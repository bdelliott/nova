{
    "flavor": {
        "OS-FLV-WITH-EXT-SPECS:extra_specs": {"key1": "value1", "key2": "value2"},
        "disk": %(int)s,
        "id": %(int)s,
        "links": [
            {
                "href": "%(host)s/v2/openstack/flavors/%(int)s",
                "rel": "self"
            },
            {
                "href": "%(host)s/openstack/flavors/%(int)s",
                "rel": "bookmark"
            }
        ],
        "name": "%(text)s",
        "ram": %(int)s,
        "vcpus": %(int)s
    }
}
