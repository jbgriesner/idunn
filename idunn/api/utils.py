from apistar.exceptions import NotFound, BadRequest
from idunn.blocks import PhoneBlock, OpeningHourBlock, InformationBlock, WebSiteBlock, ContactBlock

LONG = "long"
SHORT = "short"
DEFAULT_VERBOSITY = LONG
DEFAULT_VERBOSITY_LIST = SHORT

BLOCKS_BY_VERBOSITY = {
    LONG: [
        OpeningHourBlock,
        PhoneBlock,
        InformationBlock,
        WebSiteBlock,
        ContactBlock
    ],
    SHORT: [
        OpeningHourBlock
    ]
}

ANY = '*'

def fetch_es_poi(id, es) -> dict:
    """Returns the raw POI data
    @deprecated by fetch_es_place()

    This function gets from Elasticsearch the
    entry corresponding to the given id.
    """
    es_pois = es.search(index='munin_poi',
                        body={
                            "filter": {
                                "term": {"_id": id}
                            }
                        })

    es_poi = es_pois.get('hits', {}).get('hits', [])
    if len(es_poi) == 0:
        raise NotFound(detail={'message': f"poi '{id}' not found"})
    result = es_poi[0]['_source']

    # Flatten properties into result
    properties = {p.get('key'): p.get('value') for p in result.get('properties')}
    result['properties'] = properties
    return result

def fetch_bbox_places(es, indices, categories, bbox, max_size) -> list:
    left, bot, right, top = bbox[0], bbox[1], bbox[2], bbox[3]

    terms_filters = []
    for pair in categories:
        (cls,subcls) = pair.split(",", 1)
        if (cls,subcls) == (ANY, ANY):
            terms_filters.append([])
        elif subcls == ANY:
            terms_filters.append(["class_" + cls])
            terms_filters.append([cls])
        elif cls == ANY:
            terms_filters.append(["subclass_" + subcls])
        else:
            terms_filters.append(["class_" + cls, "subclass_" + subcls])

    should_terms = []
    for filt in terms_filters:
        if filt == []:
            should_terms.append({"match_all": {}})
        else:
            should_terms.append(
                {
                    "bool": {
                        "must": [{"term": {"poi_type.name": term}} for term in filt]
                    }
                }
            )

    bbox_places = es.search(
        index="munin_poi",
        body={
            "query": {
                "bool": {
                    "should": should_terms,
                    "minimum_should_match": 1,
                    "filter": {
                        "geo_bounding_box": {
                            "coord" : {
                                "top_left": {
                                    "lat": top,
                                    "lon": left
                                },
                                "bottom_right": {
                                    "lat": bot,
                                    "lon": right
                                }
                            }
                        }
                    }
                }
            },
            "sort": {"weight":"desc"}
        },
        size=max_size,
        timeout='3s'
    )

    bbox_places = bbox_places.get('hits', {}).get('hits', [])
    return bbox_places

def fetch_es_place(id, es, indices, type) -> list:
    """Returns the raw Place data

    This function gets from Elasticsearch the
    entry corresponding to the given id.
    """
    if type is None:
        index_name = "munin"
    elif type not in indices:
        raise BadRequest(
            status_code=400,
            detail={"message": f"Wrong type parameter: type={type}"}
        )
    else:
        index_name = indices.get(type)

    es_places = es.search(index=index_name,
        body={
            "filter": {
                "term": {"_id": id}
            }
        })

    es_place = es_places.get('hits', {}).get('hits', [])
    if len(es_place) == 0:
        raise NotFound(detail={'message': f"place {id} not found with type={type}"})

    return es_place

def build_blocks(es_poi, lang, verbosity):
    """Returns the list of blocks we want
    depending on the verbosity.
    """
    blocks = []
    for c in BLOCKS_BY_VERBOSITY.get(verbosity):
        block = c.from_es(es_poi, lang)
        if block is not None:
            blocks.append(block)
    return blocks

def get_geom(es_place):
    """Return the correct geometry from the elastic response

    A correct geometry means both lat and lon coordinates are required

    >>> get_geom({}) is None
    True

    >>> get_geom({'coord':{"lon": None, "lat": 48.858260156496016}}) is None
    True

    >>> get_geom({'coord':{"lon": 2.2944990157640612, "lat": None}}) is None
    True

    >>> get_geom({'coord':{"lon": 2.2944990157640612, "lat": 48.858260156496016}})
    {'type': 'Point', 'coordinates': [2.2944990157640612, 48.858260156496016], 'center': [2.2944990157640612, 48.858260156496016]}
    """
    geom = None
    if 'coord' in es_place:
        coord = es_place.get('coord')
        lon = coord.get('lon')
        lat = coord.get('lat')
        if lon is not None and lat is not None:
            geom = {
                'type': 'Point',
                'coordinates': [lon, lat],
                'center': [lon, lat]
            }
            if 'bbox' in es_place:
                geom['bbox'] = es_place.get('bbox')
    return geom

def get_name(properties, lang):
    """Return the Place name from the properties field of the elastic response
    Here 'name' corresponds to the POI name in the language of the user request (i.e. 'name:{lang}' field).

    If lang is None or if name:lang is not in the properties
    Then name receives the local name value

    'local_name' corresponds to the name in the language of the country where the POI is located.

    >>> get_name({}, 'fr') is None
    True

    >>> get_name({'name':'spontini', 'name:en':'spontinien', 'name:fr':'spontinifr'}, None)
    'spontini'

    >>> get_name({'name':'spontini', 'name:en':'spontinien', 'name:fr':'spontinifr'}, 'cz')
    'spontini'

    >>> get_name({'name':'spontini', 'name:en':'spontinien', 'name:fr':'spontinifr'}, 'fr')
    'spontinifr'
    """
    name = properties.get(f'name:{lang}')
    if name is None:
        name = properties.get('name')
    return name



