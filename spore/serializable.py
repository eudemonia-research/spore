import threading
import types
from spore import rlp
import importlib
import sys

# TODO: change all variables of type "field" to name "field"
#       rename all other variables called "field"
# TODO: See if it's possible to automate creation of PersonField()
# TODO: Make serialize(self) an alias for self.field_class.serialize(self)
# TODO: Deal with None serialization properly.

# NOTE: the check functions cannot result in fields() being inspected
#       the reason for this is that recursion will deadlock in this case.

class ValidationError(Exception):
    pass

def _serializable_get_locals(func):
    ret = None
    def tracer(frame, event, arg):
        nonlocal ret
        if event == 'return':
            ret = frame.f_locals.copy()
    # tracer is activated on next call, return or exception
    old_tracer = sys.getprofile()
    sys.setprofile(tracer)
    try:
        # trace the function call
        func()
    finally:
        # disable tracer and replace with old one
        sys.setprofile(old_tracer)
    return ret


class Field(object):
    _order = 0

    def __init__(self, **kwargs):
        # Give this instance a number, to restore ordering later.
        self._order = Field._order
        Field._order += 1

        if not hasattr(self, 'type'):

            class FieldInstance(object):

                def __init__(inner_self, *args, **kwargs):

                    # Add all the kwargs:
                    for key, value in kwargs.items():
                        setattr(inner_self, key, value)

                    # Add None for the fields that weren't set:
                    for key, field in self.get_fields():
                        if not hasattr(inner_self, key):
                            setattr(inner_self, key, None)

                def serialize(inner_self):
                    return self.serialize(inner_self)

                def __eq__(inner_self, other):
                    fields = self.get_fields()
                    for name, field in fields:
                        if getattr(inner_self, name) != getattr(other, name):
                            return False
                    return True

                def __setattr__(inner_self, key, value):
                    nonlocal self
                    fields = dict(self.get_fields())
                    if key not in fields:
                        raise ValidationError("No such field " + key)
                    field = fields[key]
                    if value is None:
                        if callable(field.default):
                            value = field.default()
                        else:
                            value = field.default
                    try:
                        if value is None:
                            field.check_optional(value)
                        else:
                            field.check(value)
                            field.check_type(value)
                    except ValidationError as e:
                        # Prepend the key to the exception message
                        e.args = (key + " " + e.args[0],) + e.args[1:]
                        raise
                    inner_self.__dict__[key] = value


            self.type = type(self.__class__.__name__ + 'Instance',
                             (FieldInstance,),
                             dict(self.__class__.__dict__))

        # Add the REAL make (not a class function, instance function)

        def make(inner_self, _data=None, *args, **kwargs):
            if _data is not None:
                return inner_self.deserialize(_data)
            ret = self.type(*args, **kwargs)
            self.check(ret)
            self.check_optional(ret)
            self.check_type(ret)
            return ret

        self.make = types.MethodType(make, self)

        options = _serializable_get_locals(self.__class__.default_options)
        self.default = None
        self.optional = None
        for key, value in options.items():
            setattr(self, key, value)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def default_options():
        pass

    def check(self, instance):
        pass

    def check_optional(self, value):
        if not self.optional and value is None:
            raise ValidationError("cannot be None")

    def check_type(self, value):
        if value.__class__ != self.type:
            instance_type = value.__class__.__name__
            expected_type = self.type.__name__
            raise ValidationError("is of type " + instance_type + ", expected " + expected_type)

    def get_fields(self):
        # Default serialize is to go through each of the fields.
        if not hasattr(self.__class__, 'fields'):
            raise NotImplementedError(self.__class__.__name__ + " has no fields")
        fields = _serializable_get_locals(self.__class__.fields)
        ordered_fields = []
        for key, value in fields.items():
            if isinstance(value, Field):
                ordered_fields.append((value._order, key, value))
        ordered_fields.sort()
        return [(key, value) for _, key, value in ordered_fields]

    def serialize(self, value):
        # TODO: better serialization here than RLP
        array = []
        for key, field in self.get_fields():
            attr = getattr(value, key)
            if attr is None:
                array.append(b'')
            else:
                array.append(field.serialize(attr))
        return rlp.encode(array)

    def deserialize(self, data):
        array = rlp.decode(data)
        kwargs = {}
        for (key, field), item in zip(self.get_fields(), array):
            if item is b'':
                kwargs[key] = None
            else:
                kwargs[key] = field.deserialize(item)
        return self.make(**kwargs)

    @classmethod
    def make(cls, *args, **kwargs):
        return cls().make(*args, **kwargs)


class String(Field):
    type = str
    def serialize(self, s):
        return rlp.encode(s.encode('utf-8'))
    def deserialize(self, data):
        return rlp.decode(data).decode('utf-8')

class Integer(Field):
    type = int
    def serialize(self, i):
        return i.to_bytes(max((i.bit_length()+7)>>3,1), 'big', signed=True)
    def deserialize(self, data):
        return int.from_bytes(data,'big',signed=True)

class List(Field):
    def __init__(self, inner_field, *args, **kwargs):
        self.inner_field = inner_field
        super().__init__(*args, **kwargs)

    def check_type(constraints, instances):
        if instances.__class__ != list:
            instances_type = instances.__class__.__name__
            raise ValidationError("is of type" + instances_type + ", expected list")
        for instance in instances:
            try:
                constraints.inner_field.check_type(instance)
            except ValidationError as e:
                e.args = ("inner element " + e.args[0],) + e.args[1:]
                raise
    def serialize(self, l):
        return rlp.encode([self.inner_field.serialize(i) for i in l])
    def deserialize(self, data):
        return [self.inner_field.deserialize(d) for d in rlp.decode(data)]

class Boolean(Field):
    type = bool
    def serialize(self, b):
        return (b'\x01' if b else b'\x00')
    def deserialize(self, data):
        return data == b'\x01'

class Bytes(Field):
    type = bytes
    def serialize(self, b):
        return rlp.encode(b)
    def deserialize(self, data):
        return rlp.decode(data)
