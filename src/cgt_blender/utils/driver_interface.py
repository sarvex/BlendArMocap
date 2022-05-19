from abc import abstractmethod
from dataclasses import dataclass

import bpy

from . import objects
from .mapping import CustomProps


@dataclass(frozen=True)
class DriverType:
    """ Enum for driver types. """
    SINGLE: int = 0
    BONE: int = 1
    CUSTOM: int = 2


@dataclass(frozen=True)
class ObjectType:
    """ Enum for object types"""
    OBJECT: int = 0
    BONE: int = 1
    RIG: int = 2


@dataclass(repr=True)
class DriverProperties:
    """ Driver expression include Driver Properties same as the Driver Interface.
        The properties are required to set up the Driver.
        :params
        target_object - driver gets added to obj
        provider_obj - obj providing values for driver"""
    target_object = None
    provider_obj = None
    target_rig = None

    target_type: int = ObjectType.OBJECT
    provider_type: int = ObjectType.OBJECT
    driver_type: int = DriverType.SINGLE
    property_type: str = ""

    property_name: str = ""
    data_paths: list = None
    functions: list = None

    custom_target_props: CustomProps = None

    # todo: remove overwrite
    overwrite: bool = False


@dataclass(repr=True)
class DriverContainer:
    """ Container for storing multiple drivers. """
    pose_drivers: list = None


@dataclass(repr=True)
class Driver(DriverProperties):
    """ Applies a driver to a targeted object using values gathered from a
        provider object. May stores multiple drivers and variables. """
    drivers: list = None
    variables: list = None
    assigned: bool = False

    def is_custom_property_assigned(self):
        # return if custom prop has been assigned
        self.assigned = objects.set_custom_property(self.target_object, self.property_name, True)

    def __init__(self, expression: DriverProperties):
        # requirements to check custom props
        self.target_object = expression.target_object
        self.property_name = expression.property_name

        # prevent to apply driver twice
        self.is_custom_property_assigned()
        user_prefs = objects.user_pref()
        overwrite = user_prefs.overwrite_drivers_bool  # noqa
        if self.assigned is True and overwrite is False:
            return

        # setup vars for new driver
        self.functions = expression.functions
        self.property_type = expression.property_type
        self.provider_obj = expression.provider_obj
        self.data_paths = expression.data_paths
        self.target_rig = expression.target_rig
        if self.functions is None:
            self.functions = ["", "", ""]

        # add driver placeholders to target object
        self.drivers = [self.target_object.driver_add(self.property_type, index) for index in range(3)]
        self.variables = [d.driver.variables.new() for d in self.drivers]

        # prepare and apply driver to obj
        self.prepare()
        self.apply()

    @abstractmethod
    def prepare(self):
        pass

    def apply(self):
        for idx, d in enumerate(self.drivers):
            d.driver.expression = self.functions[idx] if self.functions[idx] else "0"
