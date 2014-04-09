import threading
import sys

# TODO: Use metaclass to do field initialization stuff.
# TODO: See if it's possible to automate creation of PersonField()

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
                children = List(Person(),default=[])
                is_dead  = Boolean(default=True)
                hat      = String(null=True)
                mother   = Person(allow_hat=False,optional=True)
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

    def serialize(self):
        ret = []
        #for each of the attributes:
        #    if self.__class__.serialize_keys:
        #        ret.append(([]))


class String(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != str:
            instance_type = instance.__class__.__name__
            raise "is of type" + instance_type + ", expected str"

class Integer(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != int:
            instance_type = instance.__class__.__name__
            raise ValidationError("is of type" + instance_type + ", expected int")

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

class Boolean(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != bool:
            instance_type = instance.__class__.__name__
            raise ValidationError("is of type" + instance_type + ", expected bool")

class Bytes(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != bytes:
            instance_type = instance.__class__.__name__
            raise ValidationError("is of type" + instance_type + ", expected bytes")


#name     = String(max_length=20)
#age      = Integer(default=0)
#children = List(Person(),default=[])
#is_dead  = Boolean(default=True)
#hat      = String(null=True)
#mother   = Person(allow_hat=False)
#privkey  = Bytes()
#Self
