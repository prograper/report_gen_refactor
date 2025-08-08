"""极简 Service Locator"""

_EXTRACTORS, _GENERATORS = {}, {}

def register_extractor(cls):
    _EXTRACTORS[cls.__name__] = cls
    return cls

def get_extractor(name):
    return _EXTRACTORS[name]

def register_generator(cls):
    _GENERATORS[cls.__name__] = cls
    return cls

def get_generator(name):
    return _GENERATORS[name]
