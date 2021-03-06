# ROLE: primary-controller
# ROLE: controller

require 'spec_helper'
require 'shared-examples'
manifest = 'openstack-haproxy/openstack-haproxy-swift.pp'

describe manifest do
  shared_examples 'catalog' do

    ironic_enabled = Noop.hiera_structure 'ironic/enabled'

    # Determine if swift is used
    images_ceph = Noop.hiera_structure('storage/images_ceph', false)
    objects_ceph = Noop.hiera_structure('storage/objects_ceph', false)
    images_vcenter = Noop.hiera_structure('storage/images_vcenter', false)

    if images_ceph or objects_ceph or images_vcenter
      use_swift = false
    else
      use_swift = true
    end

    let (:bind_to_one) {
      internal_virtual_ip = Noop.hiera_structure 'network_metadata/vips/management/ipaddr'
      api_net = Noop.puppet_function 'get_network_role_property', 'swift/api', 'network'
      Noop.puppet_function 'has_ip_in_network', internal_virtual_ip, api_net
    }

    let (:bm_options) {
      bm_opt_tail = 'inter 15s fastinter 2s downinter 8s rise 3 fall 3'
      bind_to_one ? "check #{bm_opt_tail}" : "check port 49001 #{bm_opt_tail}"
    }

    let (:http_check) {
      bind_to_one ? 'httpchk HEAD /healthcheck HTTP/1.0' : 'httpchk'
    }

    let(:haproxy_config_opts) do
      {
        'option'       => [http_check, 'httplog', 'forceclose', 'http-buffer-request', 'tcp-smart-accept', 'tcp-smart-connect'],
        'timeout'      => 'http-request 10s',
        'http-request' => 'set-header X-Forwarded-Proto https if { ssl_fc }',
      }
    end

    if use_swift and !Noop.hiera('external_lb', false)

      it "should declare openstack::ha:swift class with valid params" do
        should contain_class('openstack::ha::swift').with(
          'bind_to_one' => bind_to_one,
        )
      end

      it "should properly configure swift haproxy based on ssl" do
        public_ssl_swift = Noop.hiera_structure('public_ssl/services', false)
        should contain_openstack__ha__haproxy_service('object-storage').with(
          'order'                  => '130',
          'listen_port'            => 8080,
          'public'                 => true,
          'public_ssl'             => public_ssl_swift,
          'haproxy_config_options' => haproxy_config_opts,
          'balancermember_options' => bm_options,
        )
      end

      if ironic_enabled

        baremetal_virtual_ip = Noop.hiera_structure 'network_metadata/vips/baremetal/ipaddr'

        it 'should declare ::openstack::ha::swift class with baremetal_virtual_ip' do
          should contain_class('openstack::ha::swift').with(
            'baremetal_virtual_ip' => baremetal_virtual_ip,
          )
        end

        it 'should declare openstack::ha::haproxy_service with name swift-baremetal' do
          should contain_openstack__ha__haproxy_service('object-storage-baremetal').with(
            'order'                  => '135',
            'listen_port'            => 8080,
            'public_virtual_ip'      => false,
            'internal_virtual_ip'    => baremetal_virtual_ip,
            'haproxy_config_options' => haproxy_config_opts,
            'balancermember_options' => bm_options,
          )
        end

      end

    end

  end # end of shared_examples
    test_ubuntu_and_centos manifest
end
