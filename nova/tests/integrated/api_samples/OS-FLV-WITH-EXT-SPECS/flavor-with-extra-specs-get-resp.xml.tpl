<?xml version='1.0' encoding='UTF-8'?>
<flavor xmlns:OS-FLV-WITH-EXT-SPECS="http://docs.openstack.org/compute/ext/flavor_with_extra_specs/api/v2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns="http://docs.openstack.org/compute/api/v1.1" disk="1" vcpus="1" ram="512" name="%(text)s" id="%(int)s">
    <atom:link href="http://openstack.example.com/v2/openstack/flavors/1" rel="self"/>
    <atom:link href="http://openstack.example.com/openstack/flavors/1" rel="bookmark"/>
    <OS-FLV-WITH-EXT-SPECS:extra_specs>
        <key1>%(text)s</key1>
        <key2>%(text)s</key2>
    </OS-FLV-WITH-EXT-SPECS:extra_specs>
</flavor>
