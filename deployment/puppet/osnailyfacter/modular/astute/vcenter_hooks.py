#!/usr/bin/env python
# -*- coding: utf-8 -*-

#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging
import subprocess
import yaml

from itertools import ifilter
from novaclient.client import Client
from optparse import OptionParser


def get_data_from_hiera(hiera_key, lookup_type='priority'):
    """Extract the data from Hiera using the Ruby call.

    Yes, it looks funny but other ways to do it are worse.
    I have to use the Ruby implementation of hiera here
    with the Puppet config file.

    :param lookup_type: Which lookup type should be used?
    # priority, hash, array
    :type lookup_type: str
    :param hiera_key: the key to search
    :type hiera_key: str
    :return: hiera data
    :rtype: None, str, list, dict
    """

    hiera_lookup = '''
    ruby -r hiera -r yaml -e '
    hiera = Hiera.new(:config => "/etc/puppet/hiera.yaml");
    data = hiera.lookup("{hiera_key}", nil, {{}}, nil, :{lookup_type});
    puts YAML.dump data;
    '
    '''
    try:
        command = hiera_lookup.format(
            hiera_key=hiera_key,
            lookup_type=lookup_type,
        )
        response = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
        )
        yaml_data = yaml.load(response.stdout.read())
        return yaml_data
    except subprocess.CalledProcessError as exception:
        logging.warn('Could not get Hiera data: {} Code: {} Output: {}'.format(
            hiera_key,
            exception.returncode,
            exception.output,
        ))
        return None


def check_availability_zones(nova_client, compute):
    nova_zones = nova_client.availability_zones.list()
    nova_aggregates = nova_client.aggregates.list()
    nova_zones_and_aggregates = nova_aggregates + nova_zones
    compute_zone = compute['availability_zone_name']
    present = filter(lambda item: item.to_dict().get('zoneName') ==
                     compute_zone or item.to_dict().get('availability_zone') ==
                     compute_zone, nova_zones_and_aggregates)
    if present:
        print("Zone {0} already present.".format(compute_zone))
    else:
        print("Zone {0} is missing, creating it.".format(compute_zone))
        nova_client.aggregates.create(compute_zone, compute_zone)


def check_host_in_zone(nova_client, compute):
    nova_aggregates = nova_client.aggregates.list()
    compute_zone = compute['availability_zone_name']
    compute_host = compute_zone + "-" + compute['service_name']
    present = filter(lambda aggr: compute_host in aggr.hosts, nova_aggregates)

    if present:
        print("Compute service {0} already in {1}  zone.".
              format(compute['service_name'], compute_zone))
    else:
        for aggregate in nova_aggregates:
            if aggregate.to_dict()['name'] == compute_zone:
                print("Compute service {0} not in {1} zone. Adding.".
                      format(compute['service_name'], compute_zone))
                nova_client.aggregates.add_host(aggregate, compute_host)


def main():
    credentials = get_data_from_hiera('access', 'hash')
    ssl = get_data_from_hiera('use_ssl', 'hash')
    USERNAME = credentials['user']
    PASSWORD = credentials['password']
    PROJECT_ID = credentials['tenant']
    VERSION = 2
    IP = []
    IP.append(get_data_from_hiera('keystone_vip'))
    IP.append(get_data_from_hiera('service_endpoint'))
    IP.append(get_data_from_hiera('management_vip'))
    if ssl:
        auth_protocol = 'https://'
        auth_url = ssl['keystone_internal_hostname']
        auth_port = ':5000/v2.0/'
    else:
        auth_protocol = 'http://'
        auth_url = ifilter(None, IP).next()
        auth_port = ':5000/v2.0/'

    AUTH_URL = auth_protocol + auth_url + auth_port

    parser = OptionParser()
    parser.add_option("--create_zones", action="store_true", help="Create \
                      needed availability zones and puts coresponding compute \
                      services in corresponding availability zones")
    (options, args) = parser.parse_args()

    nova = Client(VERSION, USERNAME, PASSWORD, PROJECT_ID, AUTH_URL,
                  endpoint_type='internalURL')
    vcenter_settings = get_data_from_hiera('vcenter', 'hash')

    if options.create_zones:
        for compute in vcenter_settings['computes']:
            print("---Start of Compute service {0} zone creation.---".
                  format(compute['service_name']))
            check_availability_zones(nova, compute)
            check_host_in_zone(nova, compute)
            print("----End of Compute service {0} ----".
                  format(compute['service_name']))


if __name__ == '__main__':
    main()
