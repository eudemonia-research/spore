from spore.serializable import *
import unittest

class TestSerializable(unittest.TestCase):

    def test_person(self):
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
                    return ['Hat is not allowed']

        person = Person(name="John")
        self.assertEqual(Person(person.serialize()), person)

if __name__ == '__main__':
    unittest.main()
