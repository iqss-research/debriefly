from os.path import join, dirname, abspath
import yaml


# https://stackoverflow.com/questions/38034377/object-like-attribute-access-for-nested-dictionary
class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

    @classmethod
    def from_nested_dicts(cls, data):
        """Construct nested AttrDicts from nested dictionaries."""
        if not isinstance(data, dict):
            return data
        else:
            return cls({key: cls.from_nested_dicts(data[key]) for key in data})


class Config(object):
    def __init__(self, name, filepath):
        self.name = name
        self.namespace = None
        self.file_path = None
        self.init_from_file(filepath)

    def __getattr__(self, item):
        return getattr(self.namespace, item)

    def init_from_file(self, filepath):
        self.file_path = filepath
        with open(filepath) as f:
            attr_dict = yaml.load(f, Loader=yaml.FullLoader)
        self.namespace = AttrDict.from_nested_dicts(attr_dict)

    def get_path(self, item):
        # Get a configuration value as an absolute path
        value = getattr(self.namespace, item)
        if value is None:
            return None
        assert isinstance(value, str)
        # Also works if `value` is an absolute path to begin with
        return abspath(join(dirname(self.file_path), value))
