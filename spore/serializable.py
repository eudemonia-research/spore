import threading
from spore import rlp
import sys

# TODO: Use metaclass to do field initialization stuff.
# TODO: See if it's possible to automate creation of PersonField()
# TODO: Make serialize(self) an alias for self.field_class.serialize(self)
# TODO: Deal with None serialization properly.

# NOTE: the check functions cannot result in fields() being inspected
#       the reason for this is that recursion will deadlock in this case.

class ValidationError(Exception):
    pass

class Serializable(object):
    """
    Automagically defines serialize() and a constructor on this object from
    bytes.

    Define like this:

        from serializable import *

        class Person(Serializable):

            def fields():
                name     = String(max_length=20)
                age      = Integer(default=0)
                children = List(Person(), default=[])
                is_dead  = Boolean(default=False)
                hat      = String(optional=True)
                mother   = Person(allow_hat=False, optional=True)
                privkey  = Bytes(default=b'')

            def options():
                allow_hat = True

            def check(constraints, instance):
                if constraints.allow_hat == False and instance.hat is not None:
                    raise ValidationError("has a hat, but hat is not allowed")

    And use like this:

        person = Person(name="John")
        assert Person(person.serialize()) == person

    The "optional" constraint is always provided and defaults to False. The
    field may be None if this constraint is True.

    The init() hook is called during construction, if it exists.

    check_type can also be overrided. By default, it checks that
    constraints.__class__ is equal to instance.__class__

    The check functions should return a string that can be prepended to the
    name of the field and thrown with a validation error.

    """

    _field_lock = threading.Lock()
    _options_lock = threading.Lock()
    _counter_lock = threading.Lock()
    _counter = 0
    _local = threading.local()

    def _get_locals(func):
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

    @classmethod
    def get_fields(Class):
        # FIXME: deadlock may occur when multiple threads initialize multiple
        # classes at once. It is really hard to make this stuff thread safe =/
        # Most of the time it should be fine though.

        with Class._field_lock:
            if not hasattr(Class, '_serializable_fields'):
                fields = {}
                for field, value in Class._get_locals(Class.fields).items():
                    if isinstance(value, Serializable):
                        fields[field] = value
                Class._serializable_fields = fields

        return Class._serializable_fields

    @classmethod
    def get_fields_ordered(Class):
        fields = [(value._serializable_counter, key, value) for key, value in Class.get_fields().items()]
        fields.sort()
        fields = [(key, value) for _, key, value in fields]
        return fields

    def options():
        pass

    @classmethod
    def get_options(Class):
        # FIXME: deadlock may occur when multiple threads initialize multiple
        # classes at once. It is really hard to make this stuff thread safe =/
        # Most of the time it should be fine though.

        with Class._options_lock:
            if not hasattr(Class, '_serializable_options'):
                Class._serializable_options = Class._get_locals(Class.options)

        return Class._serializable_options

    # Equal if all fields are equal.
    def __eq__(self, other):
        for field in self.__class__.get_fields():
            if getattr(self, field) != getattr(other, field):
                return False
        return True

    def __init__(self, _data=None, **kwargs):
        # Give this instance a number, to restore ordering.
        with Serializable._counter_lock:
            self._serializable_counter = Serializable._counter
            Serializable._counter += 1

        try:
            Serializable._local.depth += 1
        except AttributeError:
            Serializable._local.depth = 1

        if Serializable._local.depth == 1:
            # This instance is an actual instance, not a field definition.
            # Every assignment after this point should be checked.
            self._check_setattr = True
            fields = self.__class__.get_fields()
            for key, value in kwargs.items():
                if key in fields:
                    setattr(self, key, value)
            if _data:
                for key, val in self.deserialize_map(_data).items():
                    setattr(self, key, val)
            for field, constraints in fields.items():
                if field not in self.__dict__:
                    setattr(self, field, None)
        else:
            # This instance is a field definition.
            # Add default options and none
            options = self.__class__.get_options().copy()
            if 'optional' not in options:
                options['optional'] = False
            if 'default' not in options:
                options['default'] = None
            for key, value in kwargs.items():
                if key in options:
                    options[key] = value
            for key, value in options.items():
                setattr(self, key, value)

        Serializable._local.depth -= 1

    def serialize(self, val=None):
        if val is None: return self.serialize(self)
        fields = self.__class__.get_fields_ordered()
        array = []
        for key, value in fields:
            attr = getattr(val, key)
            if hasattr(attr, 'serialize'):
                array.append(attr.serialize())
            else:
                if attr is None:
                    array.append(b'')
                else:
                    array.append(value.serialize(attr))
        return rlp.encode(array)

    def deserialize_map(self, data):
        fields = self.__class__.get_fields_ordered()
        array = rlp.decode(data)
        kwargs = {}
        for (key, value), item in zip(fields, array):
            if item is b'':
                kwargs[key] = None
            else:
                kwargs[key] = value.deserialize(item)
        return kwargs

    def deserialize(self, data):
        return self.__class__(**self.deserialize_map(data))

    def __setattr__(self, key, value):
        if hasattr(self, '_check_setattr'):
            fields = self.__class__.get_fields()
            if key not in fields:
                raise ValidationError("No such field" + key)
            try:
                if value is None:
                    if callable(fields[key].default):
                        value = fields[key].default()
                    else:
                        value = fields[key].default
                if value is None:
                    fields[key].check_optional(value)
                else:
                    fields[key].check_type(value)
                    fields[key].check(value)
            except ValidationError as e:
                # Prepend the key to the exception message
                e.args = (key + " " + e.args[0],) + e.args[1:]
                raise

        self.__dict__[key] = value

    def check_type(constraints, instance):
        if instance.__class__ != constraints.__class__:
            instance_type = instance.__class__.__name__
            expected_type = constraints.__class__.__name__
            raise ValidationError("is of type " + instance_type + ", expected " + expected_type)

    def check_optional(constraints, instance):
        if not constraints.optional and instance is None:
            raise ValidationError("cannot be None")

    def check(constraints, instance):
        pass


class String(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != str:
            instance_type = instance.__class__.__name__
            raise "is of type" + instance_type + ", expected str"
    def serialize(self, s):
        return rlp.encode(s.encode('utf-8'))
    def deserialize(self, data):
        return rlp.decode(data).decode('utf-8')

class Integer(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != int:
            instance_type = instance.__class__.__name__
            raise ValidationError("is of type" + instance_type + ", expected int")
    def serialize(self, i):
        return i.to_bytes(max((i.bit_length()+7)>>3,1), 'big', signed=True)
    def deserialize(self, data):
        return int.from_bytes(data,'big',signed=True)

class List(Serializable):
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

class Boolean(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != bool:
            instance_type = instance.__class__.__name__
            raise ValidationError("is of type" + instance_type + ", expected bool")
    def serialize(self, b):
        return (b'\x01' if b else b'\x00')
    def deserialize(self, data):
        return data == b'\x01'

class Bytes(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != bytes:
            instance_type = instance.__class__.__name__
            raise ValidationError("is of type" + instance_type + ", expected bytes")
    def serialize(self, b):
        return rlp.encode(b)
    def deserialize(self, data):
        return rlp.decode(data)
