import threading
import sys

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
                    raise ValidationError('hat is not allowed')

    And use like this:

        person = Person(name="John")
        assert Person(person.serialize()) == person

    You get the constraints "null", "none", "allow_none", "allow_null", and
    "optional" for free, all of which mean the same thing and default to False.
    They are always checked.

    The init() hook is called during construction, if it exists.

    check_type can also be overrided. By default, it checks that
    constraints.__class__ is equal to instance.__class__

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
        sys.setprofile(tracer)
        try:
            # trace the function call
            func()
        finally:
            # disable tracer and replace with old one
            sys.setprofile(None)
        return ret

    @classmethod
    def get_fields(Class):
        # FIXME: deadlock may occur when multiple threads initialize multiple
        # classes at once. It is really hard to make this stuff thread safe =/
        # Most of the time it should be fine though.

        with Class._field_lock:
            if not hasattr(Class, '_serializable_fields'):
                Class._serializable_fields = Class._get_locals(Class.fields)

        return Class._serializable_fields

    @classmethod
    def get_options(Class):
        # FIXME: deadlock may occur when multiple threads initialize multiple
        # classes at once. It is really hard to make this stuff thread safe =/
        # Most of the time it should be fine though.

        with Class._options_lock:
            if not hasattr(Class, '_serializable_options'):
                Class._serializable_options = Class._get_locals(Class.options)

        return Class._serializable_options

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
            print("Got called with kwargs: ",kwargs)
            # This instance is an actual instance, not a field definition.
            # Every assignment after this point should be checked.
            self._check_setattr = True
            fields = self.__class__.get_fields()
            for key, value in kwargs.items():
                if key in fields:
                    setattr(self, key, value)
            for field, constraints in fields.items():
                print("key is",field,"constraints is",constraints)
                if field not in self.__dict__:
                    setattr(self, field, None)
        else:
            # This instance is a field definition.
            pass

        Serializable._local.depth -= 1

    def __setattr__(self, key, value):
        if hasattr(self, '_check_setattr'):
            pass
        self.__dict__[key] = value

    def check_type(constraints, instance):
        if instance.__class__ != constraints.__class__:
            instance_type = instance.__class__.__name__
            expected_type = constraints.__class__.__name__
            message = instance_type + " type is not " + expected_type
            raise ValidationError(message)

    def check_none(constraints, instance):
        if not (constraints.none or
                constraints.null or
                constraints.optional or
                constraints.allow_none or
                constraints.allow_null) and instance is None:
            raise ValidationError("instance cannot be None")


    def serialize(self):
        ret = []
        #for each of the attributes:
        #    if self.__class__.serialize_keys:
        #        ret.append(([]))


class String(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != str:
            instance_type = instance.__class__.__name__
            raise ValidationError(instance_type + " type is not str")

class Integer(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != int:
            instance_type = instance.__class__.__name__
            raise ValidationError(instance_type + " type is not int")

class List(Serializable):
    def __init__(self, inner_field, *args, **kwargs):
        self.inner_field = inner_field
        super().__init__(*args, **kwargs)

    def check_type(constraints, instances):
        if instances.__class__ != list:
            instances_type = instances.__class__.__name__
            raise ValidationError(instances_type + " type is not list")
        for instance in instances:
            constraints.inner_field.check_type(instance)

class Boolean(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != bool:
            instance_type = instance.__class__.__name__
            raise ValidationError(instance_type + " type is not bool")

class Bytes(Serializable):
    def check_type(constraints, instance):
        if instance.__class__ != bytes:
            instance_type = instance.__class__.__name__
            raise ValidationError(instance_type + " type is not bytes")


#name     = String(max_length=20)
#age      = Integer(default=0)
#children = List(Person(),default=[])
#is_dead  = Boolean(default=True)
#hat      = String(null=True)
#mother   = Person(allow_hat=False)
#privkey  = Bytes()
#Self
