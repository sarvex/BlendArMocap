import importlib
from enum import Enum

from blender import objects, abs_rigging
from utils import m_V

importlib.reload(m_V)
importlib.reload(objects)
importlib.reload(abs_rigging)


class RigPose(abs_rigging.BpyRigging):
    # todo: set ik_fk for driver bones
    # bpy.context.object.pose.bones["thigh_parent.R"]["IK_FK"] = 0
    # bpy.context.object.pose.bones["thigh_parent.R"]["IK_Stretch"] = 0

    def __init__(self, armature, driver_objects: list):
        self.relation_mapping_lst = []
        self.method_mapping = {
            # todo: arm specific driver method
            DriverType.arm_driver: self.add_driver_batch,
            DriverType.constraint: self.add_constraint
        }

        self.pose_bones = armature.pose.bones
        self.arm_bones = [
            ["upper_arm_fk.L", "forearm_fk.L"],
            ["forearm_fk.L", "hand_fk.L"],

            ["upper_arm_fk.R", "forearm_fk.R"],
            ["forearm_fk.R", "hand_fk.R"],
        ]

        # offsets and avg data based on rigify rig
        self.avg_arm_length = self.get_average_scale(self.arm_bones, self.pose_bones)
        self.left_arm_offset = self.get_location_offset(self.pose_bones, "upper_arm_ik.L", "cgt_right_shoulder")
        self.right_arm_offset = self.get_location_offset(self.pose_bones, "upper_arm_ik.R", "cgt_left_shoulder")

        self.multi_user_driver_dict = {
            "cgt_left_shoulder": ["cgt_left_hand_ik_driver", "cgt_left_forearm_ik_driver"],
            "cgt_right_shoulder": ["cgt_right_hand_ik_driver", "cgt_right_forearm_ik_driver"],
            "cgt_left_hip": ["cgt_left_shin_ik_driver", "cgt_left_foot_ik_driver"],
            "cgt_right_hip": ["cgt_right_shin_ik_driver", "cgt_right_foot_ik_driver"]
        }

        # references for setting drivers and constraints
        self.references = {
            # DRIVERS
            # arms
            "cgt_left_shoulder": [DriverType.arm_driver, self.driver_z_sca2loc_attr()],
            "cgt_left_wrist": [DriverType.arm_driver,
                               self.driver_loc2loc_sca_attr("cgt_left_hand_ik_driver", self.left_arm_offset)],
            "cgt_left_elbow": [DriverType.arm_driver,
                               self.driver_loc2loc_sca_attr("cgt_left_forearm_ik_driver", self.left_arm_offset)],
            "cgt_right_shoulder": [DriverType.arm_driver, self.driver_z_sca2loc_attr()],
            "cgt_right_wrist": [DriverType.arm_driver,
                                self.driver_loc2loc_sca_attr("cgt_right_hand_ik_driver", self.right_arm_offset)],
            "cgt_right_elbow": [DriverType.arm_driver,
                                self.driver_loc2loc_sca_attr("cgt_right_forearm_ik_driver", self.right_arm_offset)],

            # legs
            "cgt_left_hip": [DriverType.arm_driver, self.driver_z_sca2loc_attr()],
            "cgt_left_knee": [DriverType.arm_driver,
                              self.driver_loc2loc_sca_attr("cgt_left_shin_ik_driver", [0, 0, 0])],
            "cgt_left_ankle": [DriverType.arm_driver,
                               self.driver_loc2loc_sca_attr("cgt_left_foot_ik_driver", [0, 0, 0])],
            "cgt_right_hip": [DriverType.arm_driver, self.driver_z_sca2loc_attr()],
            "cgt_right_knee": [DriverType.arm_driver,
                               self.driver_loc2loc_sca_attr("cgt_right_shin_ik_driver", [0, 0, 0])],
            "cgt_right_ankle": [DriverType.arm_driver,
                                self.driver_loc2loc_sca_attr("cgt_right_foot_ik_driver", [0, 0, 0])],

            # CONSTRAINTS
            # def rots
            "hip_center": [DriverType.constraint, ["hips", "COPY_ROTATION"]],
            "shoulder_center": [DriverType.constraint, ["chest", "COPY_ROTATION"]],
            # arms (mapped mirrored)
            "cgt_left_hand_ik_driver": [DriverType.constraint, ["hand_ik.R", "COPY_LOCATION"]],
            "cgt_right_hand_ik_driver": [DriverType.constraint, ["hand_ik.L", "COPY_LOCATION"]],
            "cgt_left_forearm_ik_driver": [DriverType.constraint, ["forearm_tweak.R", "COPY_LOCATION"]],
            "cgt_right_forearm_ik_driver": [DriverType.constraint, ["forearm_tweak.L", "COPY_LOCATION"]],
            # legs (mapped mirrored)
            "cgt_right_foot_ik_driver": [DriverType.constraint, ["foot_ik.L", "COPY_LOCATION"]],
            "cgt_left_foot_ik_driver": [DriverType.constraint, ["foot_ik.L", "COPY_LOCATION"]],
            "cgt_left_shin_ik_driver": [DriverType.constraint, ["shin_tweak.L", "COPY_LOCATION"]],
            "cgt_right_shin_ik_driver": [DriverType.constraint, ["shin_tweak.R", "COPY_LOCATION"]],
        }

        # setup relations between rig and drivers, then apply the drivers to the rig
        self.set_relation_dict(driver_objects)
        self.apply_drivers()

    # region rig driver relation setup
    def set_relation_dict(self, driver_objects: list):
        # setting driver target for multi users
        driver_names = [obj.name for obj in driver_objects]

        # dict containing drivers and required params
        for ref in self.references:
            if ref in driver_names:
                idx = driver_names.index(ref)
                driver_obj = driver_objects[idx]
                driver_type = self.references[ref][0]

                # multi user driver
                if ref in self.multi_user_driver_dict:
                    references = self.references[ref][1]
                    for t, driver_target in enumerate(self.multi_user_driver_dict[ref]):
                        refs = references.copy()  # copy refs to avoid overwrites
                        refs[0] = driver_target
                        rel = MappingRelation(driver_obj, driver_type, refs)
                        self.relation_mapping_lst.append(rel)

                # single user driver
                else:
                    relation = MappingRelation(driver_obj, driver_type, self.references[ref][1])
                    self.relation_mapping_lst.append(relation)
            else:
                print("Mapping failed for", ref, "in rigify_pose")

    # endregion

    # region apply drivers
    def apply_drivers(self):
        pose_bone_names = [bone.name for bone in self.pose_bones]

        for driver in self.relation_mapping_lst:
            values = driver.values[0]

            if driver.driver_type == DriverType.arm_driver:
                target = objects.get_object_by_name(values[0])

                # add_driver_batch(driver_target, driver_source, prop_source, prop_target, data_path, func)
                add_driver_batch = self.method_mapping[driver.driver_type]
                add_driver_batch(target, driver.source, values[1], values[2], values[3], values[4])

            elif driver.driver_type == DriverType.constraint:
                if values[0] in pose_bone_names:
                    idx = pose_bone_names.index(values[0])
                    pose_bone = self.pose_bones[idx]
                    # add_constraint(bone, target, constraint)
                    add_constraint = self.method_mapping[driver.driver_type]
                    add_constraint(pose_bone, driver.source, values[1])

    # endregion

    # region driver setup
    @staticmethod
    def driver_z_sca2loc_attr():
        attribute = [
            None, "location", "scale",
            ["scale.z", "scale.z", "scale.z"],
            ["", "", ""]]
        return attribute

    @staticmethod
    def get_location_offset(pose_bones, bone_name, target):
        bone_pos = pose_bones[bone_name].head
        ob = objects.get_object_by_name(target)
        tar = ob.location
        offset = bone_pos - tar
        return offset

    def driver_loc2loc_sca_attr(self, driver_target, offset):
        attribute = [
            driver_target, "location", "location",
            ["location.x", "location.y", "location.z"],
            [f"{offset[0]}+{self.avg_arm_length}/(scale) *",
             f"{offset[1]}+{self.avg_arm_length}/(scale) *",
             f"{offset[2]}+{self.avg_arm_length}/(scale) *"]]
        return attribute
    # endregion


class DriverType(Enum):
    arm_driver = 0
    constraint = 1


class MappingRelation:
    source = None
    values = None
    diver_type = None

    def __init__(self, source, driver_type: DriverType, *args):
        self.source = source
        self.driver_type = driver_type
        self.values = args
