# -*- coding: UTF-8 -*-
import re 

from ...utils.path import Path


__all__ = ["Config", "Option"]


class Config(dict):
    """ Enhanced dictionary for handling Option instances as its keys. """
    bind = True  # class attribute used to bind a parent class to a Config
                 #  instance
    def __init__(self, *args, **kwargs):
        self.__d = {}
        self.update(*args, **kwargs)
    
    def __getitem__(self, key):
        """ Custom method for getting an item, returning the original value from
             the current Config instance or, if the key does not exist and this
             instance has a parent, try to get it from the parent. """
        if isinstance(key, Option):
            key = key.name
        try:
            return self.__d[key][1]
        except KeyError:
            if hasattr(self, "console") and self.console.parent is not None:
                return self.console.parent.config[key]
            raise KeyError(key)
    
    def __setitem__(self, key, value):
        """ Custom method for setting an item, keeping the original value in a
             private dictionary. """
        if not isinstance(key, Option):
            if not isinstance(key, tuple):
                key = (key, )
            key = Option(*key)
        tmp = key
        key = key.bind(self)  # get an existing instance or the new one
        if tmp is not key: 
            del tmp  # if an instance already existed, remove the new one
        # keep track of the previous value
        key.old_value = key.value if self.__d.get(key.name) else None
        # then assign the new one
        self.__d[key.name] = (key, value)
        if not key.validate():
            raise ValueError("Invalid value")
        super(Config, self).__setitem__(key, value)
        try:
            key.callback()
        except Exception as e:
            self._last_error = str(e)
            #self.console.logger.exception(e)
        if key._reset:
            self.console.reset()
    
    def copy(self, config, key):
        """ Copy an option based on its key from another Config instance. """
        self[config.option(key)] = config[key]

    def items(self):
        """ Return (key, descr, value, required) instead of (key, value). """
        for o in sorted(self, key=lambda x: x.name):
            yield str(o.name), o.description or "", o.value, o.required

    def keys(self):
        """ Return string keys (like original dict). """
        for k in sorted(self.__d.keys()):
            yield k

    def option(self, key):
        """ Return Option instance from key. """
        if isinstance(key, Option):
            key = key.name
        try:
            return self.__d[key][0]
        except KeyError:
            if hasattr(self, "console") and self.console.parent is not None:
                return self.console.parent.config.option(key)
            raise KeyError(key)

    def setdefault(self, key, value=None):
        """ Custom method for forcing the use of the modified __setitem__. """
        if key not in self:
            self[key] = value
        return self[key]

    def update(self, *args, **kwargs):
        """ Custom update method for handling update of another Config and
             forcing the use of the modified __setitem__. """
        if len(args) > 0:
            if len(args) > 1:
                raise TypeError("update expected at most 1 arguments, got %d" \
                                % len(args))
            d = args[0]
            for k in d:
                self[k] = d[k]
        for k, v in kwargs.items():
            self[k] = v


class Option(object):
    """ Class for handling an option with its parameters while using it as key
         for a Config dictionary. """
    _instances = {}
    _reset     = False
    old_value  = None
    
    def __init__(self, name, description=None, required=False, choices=None,
                 transform=None, validate=None, callback=None):
        self.name = name
        self.description = description
        self.required = required
        if choices is bool:
            choices = ["true", "false"]
        self.choices = choices
        self.__set_func(transform, "transform")
        if validate is None and choices is not None:
            validate = lambda s: str(s.value).lower() in \
                                 [str(_).lower() for _ in s.choices]
        self.__set_func(validate, "validate")
        self.__set_func(callback, "callback")
    
    def __repr__(self):
        """ Custom representation method. """
        return "<{}: {}>".format(self.name, self.value)
    
    def __str__(self):
        """ Custom string method. """
        return "<{}: {}>".format(self.name, self.value)
    
    def __set_func(self, func, name):
        """ Set a function, e.g. for manipulating option's value. """
        if func is None:
            func = lambda *a, **kw: a[-1] if len(a) > 0 else None
        if isinstance(func, type(lambda:0)):
            setattr(self, name, func.__get__(self, self.__class__))
        else:
            raise Exception("Bad {} lambda".format(name)) 
    
    def bind(self, parent):
        """ Register this instance as a key of the given Config or retrieve the
             already existing one. """
        o, i = Option._instances, id(parent)
        o.setdefault(i, {})
        if o[i].get(self.name) is None:
            self.config = parent
            o[i][self.name] = self
        else:
            o[i][self.name].config = parent
        return o[i][self.name]
    
    def copy(self):
        """ Copy option information to a new Option instance. """
        return Option(self.name, self.description, self.required, self.choices,
                      self.transform, self.validate, self.callback)
    
    @property
    def input(self):
        """ Original input value. """
        if hasattr(self, "config"):
            return self.config[self]
        else:
            raise Exception("Unbound option {}" .format(self.name))
    
    @property
    def value(self):
        """ Normalized value attribute. """
        value = self.input
        if self.required and value is None:
            raise ValueError("{} must be defined" .format(self.name))
        try:
            # try to expand format variables using console's attributes
            kw = {}
            for n in re.findall(r'\{([a-z]+)\}', str(value)):
                kw[n] = self.config.console.__dict__.get(n, "")
            try:
                value = value.format(**kw)
            except:
                pass
        except AttributeError as e:  # occurs when console is not linked to
            pass                     #  config (i.e. at startup)
        # expand and resolve paths
        if self.name.endswith("FOLDER") or self.name.endswith("WORKSPACE"):
            # this will ensure that every path is expanded
            value = str(Path(value, expand=True))
        # convert common formats to their basic types
        try:
            if value.isdigit():
                value = int(value)
            if value.lower() in ["false", "true"]:
                value = value.lower() == "true"
        except AttributeError:  # occurs e.g. if value is already a bool
            pass
        # then try to transform using the user-defined function
        if isinstance(self.transform, type(lambda:0)) and \
            self.transform.__name__ == (lambda:0).__name__:
            value = self.transform(value)
        return value
