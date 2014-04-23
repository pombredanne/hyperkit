# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import logging
import shutil

from hyperkit.cloudinit import CloudConfig, Seed, MetaData
from .machine import MachineInstance, Hypervisor
from .command import Command
from .vboxmanage import VBoxManage
from .qemu_img import QEmuImg

logger = logging.getLogger(__name__)

class VBoxMachineInstance(MachineInstance):

    name = "vbox"

    # takes a long time to start the tools
    timeout = 300

    def __init__(self, directory, instance_id):
        self.directory = directory
        self.instance_id = instance_id
        self.vboxmanage = VBoxManage()

    @property
    def id(self):
        return self.instance_id

    def _start(self, gui=False):
        s_type = {
            True: "gui",
            False: "headless",
            }[gui]
        self.vboxmanage("startvm", type=s_type, name=self.instance_id)

    def _stop(self, force=False):
        button = {False: "acpipowerbutton", True: "poweroff"}.get(force)
        self.vboxmanage("controlvm", name=self.instance_id, button=button)

    def _destroy(self):
        self.vboxmanage("unregistervm", name=self.instance_id)
        shutil.rmtree(os.path.join(self.directory, self.instance_id))

    def get_ip(self):
        self.vboxmanage("guestproperty", name=self.instance_id, property="/VirtualBox/GuestInfo/Net/0/V4/IP")
        if s.startswith("Value: "):
            return s.split(" ", 1)[1]


class VBoxCloudConfig(CloudConfig):
    runcmd = [
        ['mount', '/dev/sr1', '/mnt'],
        ['/mnt/VBoxLinuxAdditions.run'],
        ['umount', '/mnt'],
    ]


class VBoxUbuntuCloudConfig(VBoxCloudConfig):
    #package_update = True
    #package_upgrade = True
    packages = ['build-essential']


class VBoxFedoraCloudConfig(VBoxCloudConfig):
    pass


class VirtualBox(Hypervisor):

    hypervisor_id = "vbox"
    directory = os.path.expanduser("~/VirtualBox VMs")
    instance = VBoxMachineInstance

    configs = {
        "ubuntu": VBoxUbuntuCloudConfig,
        "fedora": VBoxFedoraCloudConfig,
    }

    ostype = {
        "ubuntu": "Ubuntu_64",
        "fedora": "Fedora_64",
        None: "Linux_64",
    }

    def __init__(self):
        self.vboxmanage = VBoxManage()
        self.qemu_img = QEmuImg()

    def __str__(self):
        return "VirtualBox"

    @property
    def present(self):
        return createvm.pathname is not None

    def create(self, spec):
        """ Create a new virtual machine in the specified directory from the base image. """

        instance_id = self.get_instance_id(spec)
        instance_dir = os.path.join(self.directory, instance_id)
        # create the directory to hold all the bits
        logger.info("Creating directory %s" % (instance_dir, ))
        os.mkdir(instance_dir)

        logger.info("Creating virtual machine")
        self.vboxmanage("createvm", name=instance_id, directory=self.directory, ostype=self.ostype[spec.image.distro])
        self.vboxmanage("configurevm", name=instance_id, memsize=spec.hardware.memory)

        logger.info("Creating disk image from %s" % (spec.image, ))
        # create the disk image and attach it
        disk = os.path.join(instance_dir, instance_id + "_disk1.vdi")
        self.qemu_img("convert", source=spec.image.fetch(self.image_dir), destination=disk, format="vdi")
        self.vboxmanage("create_sata", name=instance_id)
        self.vboxmanage("attach_disk", name=instance_id, disk=disk)

        # create the seed ISO
        logger.info("Creating cloudinit seed")
        config_class = self.configs[spec.image.distro]
        cloud_config = config_class(spec.auth)
        meta_data = MetaData(spec.name)
        seed = Seed(instance_dir, cloud_config=cloud_config, meta_data=meta_data)
        seed.write()

        logger.info("Attaching devices")
        # connect the seed ISO and the tools ISO
        self.vboxmanage("create_ide", name=instance_id)
        self.vboxmanage("attach_ide", name=instance_id, port="0", device="0", filename=seed.pathname)
        self.vboxmanage("attach_ide", name=instance_id, port="0", device="1", filename="/usr/share/virtualbox/VBoxGuestAdditions.iso")
        logger.info("Machine created")
        return self.load(instance_id)

__all__ = [VirtualBox]
