from spore.serializable import *
import unittest

class TestSerializable(unittest.TestCase):

    def test_person(self):

        class Person(Field):

            def fields():
                name     = String(max_length=20)
                age      = Integer(default=0)
                children = List(Person(), default=[])
                is_dead  = Boolean(default=False)
                hat      = String(optional=True)
                mother   = Person(allow_hat=False, optional=True)
                privkey  = Bytes(default=b'')

            def default_options():
                allow_hat = True

            def check(options, instance):
                if options.allow_hat == False and instance.hat is not None:
                    raise ValidationError("Hat is not allowed")

            def say_hello(self):
                return "Hello, I'm " + self.name

        # Creates an object with those fields.
        person = Person.make(name="John")
        self.assertEqual(Person.make(person.serialize()), person)
        self.assertEqual(person.say_hello(), "Hello, I'm John")
        self.assertRaises(ValidationError, Person(allow_hat=False).make, name='John', hat='Fedora')
        person.age = 10
        def do_validation_error():
            person.is_dead = 12
        self.assertRaises(ValidationError, do_validation_error)
        person.is_dead = True
        person.privkey = b'1234'
        self.assertEqual(Person.make(person.serialize()), person)
        def do_validation_error():
            person.name = ('too long'*30)
        self.assertRaises(ValidationError, do_validation_error)

if __name__ == '__main__':
    unittest.main()
