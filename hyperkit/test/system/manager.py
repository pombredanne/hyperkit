#! /usr/bin/env python

"""

These are System tests

They will only work if you have all the moving parts available

"""

import argparse
import wingdbstub
import datetime
import os
import time
import subprocess
import random
import shutil
import threading




class SystemTest:

    timeout = 500
    systems = ["vbox", "vmware"]

    distros = [{
        "name": "ubuntu",
        "releases": ["14.04", "12.04"],
        "architectures": ["amd64", "i386"],
    }, {
        "name": "fedora",
        "releases": ["20", "19"],
        "architectures": ["x86", "x86_64"],
    }]

    def __init__(self, vm_dir, report_dir, hypervisors, releases=()):
        self.vm_dir = vm_dir
        self.report_dir = report_dir
        self.hypervisors = hypervisors
        self.releases = releases
        if self.releases:
            for d, r, a in self.releases:
                if not self.check_release(d, r, a):
                    print "Bad release spec: %s/%s/%s" % (d, r, a)
                    raise SystemExit
        if not os.path.exists(report_dir):
            os.mkdir(report_dir)
        if not os.path.exists(vm_dir):
            os.mkdir(vm_dir)

    def check_release(self, d, r, a):
        for e in self.distros:
            if e['name'] == d:
                if r not in e['releases']:
                    print "Release", r, "not recognised for distro", d
                    return False
                if a not in e['architectures']:
                    print "Architecture", a, "not recognised for distro", d
                    return False
                return True
        return False

    def should_test(self, hypervisor, distro, release, architecture):
        if self.hypervisors and hypervisor not in self.hypervisors:
            return False
        if self.releases and (distro, release, architecture) not in self.releases:
            return False
        return True

    def killkillkill(self, p):
        if p.poll() is None:
            print "Process taking too long, terminating"
            try:
                p.kill()
            except:
                # ignore race condition
                pass

    def hyperkit(self, hypervisor, command, args):
        command = ["hyperkit",
                   "--debug",
                   "--directory", self.vm_dir,
                   "--hypervisor", hypervisor,
                   command,
                   ] + args
        print "Executing", " ".join(command)
        t = time.time()
        p = subprocess.Popen(command,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        th = threading.Timer(self.timeout, self.killkillkill, [p])
        th.start()
        stdout, stderr = p.communicate()
        th.cancel()
        print "Command completed in %0.2fs" % (time.time() - t)
        #for l in stderr.splitlines():
        #    print l
        return dict(stdout=stdout, stderr=stderr, code=p.returncode)

    def generate_name(self):
        def rndchr():
            for i in range(10):
                yield chr(65 + random.randint(0, 25))
        return "".join(rndchr())

    def test_system(self):
        print "Running system tests"
        print "Creating virtual machines in", self.vm_dir
        print "Writing reports to", self.report_dir
        if self.hypervisors:
            print "Limiting tests to only hypervisors:", self.hypervisors
        else:
            print "Testing all hypervisors"
        if self.releases:
            print "Limiting tests to only the following releases:"
            for d, r, a in self.releases:
                print "    Distro:", d, "Release:", r, "Arch:", a
        else:
            print "Testing all systems"
        d = datetime.datetime.now()
        self.run = "%04d-%02d-%02d-%010d" % (d.year, d.month, d.year, time.time())
        self.rundir = os.path.join(self.report_dir, self.run)
        os.mkdir(self.rundir)
        start = time.time()
        for system in self.systems:
            system_start = time.time()
            for distro in self.distros:
                distro_start = time.time()
                for release in distro["releases"]:
                    release_start = time.time()
                    for arch in distro["architectures"]:
                        if self.should_test(system, distro['name'], release, arch):
                            self.exec_test( system=system, distro=distro["name"], release=release, arch=arch)
                        else:
                            print "Skipping", system, distro['name'], release, arch
                    print "Release tested in %0.2fs" % (time.time() - release_start, )
                print "Distro tested in %0.2fs" % (time.time() - distro_start, )
            print "System tested in %0.2fs" % (time.time() - system_start, )
        print "Tests completed in %0.2fs" % (time.time() - start, )

    def exec_test(self, system, distro, release, arch):
        print "Testing", system, distro, release, arch
        name = self.generate_name()
        print "Creating virtual machine", name
        instance = "-".join([system, distro, release, arch])

        def run(command, args):
            r = self.hyperkit(system, command, args)
            for key, value in r.items():
                lf = open(os.path.join(self.rundir, "%s.%s.%s" % (instance, command, key)), "w")
                lf.write(str(value))
            if r['code'] != 0:
                raise OSError(r)
            return r['stdout']

        try:
            run("create", [name, distro, release, arch])
        except OSError:
            print "Could not create VM"
            return
        try:
            path = run("path", [name])
            run("start", [name])
            run("wait", [name])
        except OSError:
            print "VM starting failed, will try to stop and destroy"
        try:
            run("stop", [name])
            # stopping takes time
            time.sleep(10)
        except OSError:
            print "VM Stopping failed, will try to destroy anyway"
        finally:
            self.analyze_image(system, path)
        run("destroy", [name])

    def analyze_image(self, system, path):
        """ Analyze a disk image """
        pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory", default="/var/tmp/hyperkit_test", help="directory to put test vms in")
    parser.add_argument("-o", "--output", default=os.path.realpath("test_reports"), help = "write test reports to this directory")
    parser.add_argument("-H", "--hypervisor", choices = ("vmware", "vbox"), nargs="*", help="hypervisor to test (by default all present are tested)")
    parser.add_argument("release", nargs="*", help="distro/release/architecture")
    args = parser.parse_args()
    release = [tuple(x.split("/", 2)) for x in args.release]
    t = SystemTest(args.directory, args.output, args.hypervisor, release)
    t.test_system()