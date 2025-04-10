.. kalib documentation master file, created by
   sphinx-quickstart on Sat Dec 21 03:42:51 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

kalib documentation
===================

Property Documentation
======================

The `Property` class is a versatile descriptor used for managing attributes in a class. Below are the different variants of the `Property` class:

Instance Properties
-------------------

- **Cached**: Replaces the data-descriptor with a calculated result, supporting asynchronous operations.

  .. code-block:: python

      class Property(BaseProperty):
          Cached = Cached

- **Bind**: Just replaces the getter with a calculated result for simple cases.

  .. code-block:: python

      class Property(BaseProperty):
          Bind = cached_property

Class Properties
----------------

- **Class**: Passes the class as the first positional argument.

  .. code-block:: python

      class Property(BaseProperty):
          Class = ClassProperty

- **Class.Parent**: Passes the original class where the decorator is used, then replaces its own data-descriptor with a calculated result in the original parent.

  .. code-block:: python

      class Property(BaseProperty):
          Class.Parent = ClassCachedProperty

- **Class.Cached**: Passes the inherited class and sets the child class attribute with a calculated result.

  .. code-block:: python

      class Property(BaseProperty):
          Class.Cached = InheritedClass.make_from(ClassCachedProperty)

- **Mixed**: Can be used with either a class or an instance.

  .. code-block:: python

      class Property(BaseProperty):
          Mixed = MixedProperty

- **Mixed.Cached**: Replaces the data-descriptor with a calculated result for instances, but when used in a class context, passes the class and just returns the result.

  .. code-block:: python

      class Property(BaseProperty):
          Mixed.Cached = InheritedClass.make_from(MixedCachedProperty)

.. toctree::
   :maxdepth: 2
   :caption: Contents:
