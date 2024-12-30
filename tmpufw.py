#!/usr/bin/env python3
"""
Temporarily apply `ufw` rules

This script allows you to add rules to `ufw` (Uncomplicated Firewall) with a
time to live. You can then run the script as a cronjob (with the --clean flag)
to clean up (remove) the expired rules.

Arguments:
    -h, --help                       show the help message and exit
    -s, --status                     show rule list with expirations
    -c, --clean                      clean up expired rules
    -r RULE, --rule RULE             rule to be added to `ufw`
    -p POSITION, --position POSITION position to add the rule
    -t TTL, --ttl TTL                time to live for the rule
"""
__author__ = ['Joshua Sherman', "Jonas Schmid"]
__file__ = 'tmpufw'
__license__ = 'MIT'
__status__ = 'Production'
__version__ = '2.0.0'

import os
from argparse import ArgumentParser
import argparse
from datetime import datetime, timedelta
from os import getpid, makedirs, path, remove
from shutil import move
from subprocess import CalledProcessError, check_output, STDOUT
from sys import exit
from time import mktime, time
import re

regex = re.compile(r'((?P<days>\d+?)d)?((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?')


def parse_time(time_str):
    parts = regex.match(time_str.lower().replace(" ", ""))
    if not parts:
        return timedelta(days=30)

    parts = parts.groupdict()
    time_params = {}
    for name, param in parts.items():
        if param:
            time_params[name] = int(param)
    if timedelta(**time_params).total_seconds() <= 0:
        print("Something with the timereading missmatched, we just take the default 30days")
        return timedelta(days=30)
    return timedelta(**time_params)


dry_run = False


def main():
    parser = argparse.ArgumentParser(description='Temporarily apply `ufw` rules')
    parser.add_argument("-s", "--status", action="store_true", help="show rule list with expirations")
    parser.add_argument("-c", "--clean", action="store_true", help="clean up expired rules")
    parser.add_argument("-r", "--rule", help="rule to be added to `ufw`")
    parser.add_argument("-p", "--position", default=1, help="position to add the rule")
    parser.add_argument("-t", "--ttl", default="30d", help="time to live for the rule")
    parser.add_argument("--dry-run", action="store_true", help="dry run")
    args = parser.parse_args()
    global dry_run
    dry_run = args.dry_run
    if not dry_run:
        # Our file names
        pid_file = '/var/run/' + __file__ + '.pid'
        rules_file = '/usr/local/share/' + __file__ + '/rules'
        tmp_rules_file = '/tmp/' + __file__ + '-rules'
    else:
        pid_file = "./tmp/" + __file__ + ".pid"
        rules_file = "./tmp/" + __file__ + "/rules"
        tmp_rules_file = "./tmp/" + __file__ + "-rules"
    if args.status:
        if path.exists(rules_file):
            print("Expiration\t\tRule")
            print('=' * 80)

            for line in open(rules_file, 'r'):
                # Breaks apart line into expiration timestamp and rule
                timestamp, rule = line.strip("\n").split(' ', 1)

                print(str(datetime.fromtimestamp(float(timestamp))) + "\t" + rule)
        # We removed error handling, as the errors were just passed up
        else:
            raise Exception("There are no rules to display")

    if args.clean:
        # Checks and creates PID file
        if path.exists(pid_file):
            raise Exception(__file__ + " is already running")
        else:
            try:
                handle = open(pid_file, 'w')
                handle.write(str(getpid()))
                handle.close()
            except IOError:
                raise Exception("unable to create PID file: " + pid_file)
            # Checks for the rules file
            if path.exists(rules_file):

                tmp_rules_filehandle = open(tmp_rules_file, 'a')
                current_time = datetime.now().timestamp()
                # Loop through the rules lines
                for line in open(rules_file, 'r'):
                    # Breaks apart line into expiration timestamp and rule
                    timestamp, rule = line.strip("\n").split(' ', 1)

                    # Checks if rule has expired
                    if current_time < float(timestamp):
                        tmp_rules_filehandle.write(line)
                        print(str(datetime.fromtimestamp(float(timestamp))) + "\tskipped rule\t" + rule)

                    else:
                        try:
                            ufw_delete(rule)
                            print(str(datetime.fromtimestamp(time())) + "\tdeleted rule\t" + rule)
                        except CalledProcessError as error:
                            ufw_error(error)
                os.sync()
                tmp_rules_filehandle.close()
                # Moves the tmp file to the rules file
                move(tmp_rules_file, rules_file)
            remove(pid_file)  # Removes the PID
    if args.rule:
        rules_path = path.dirname(rules_file)

        if not path.exists(rules_path):
            makedirs(rules_path)

        timestamp = datetime.now().timestamp() + parse_time(args.ttl).total_seconds()
        handle = open(rules_file, "r")
        if args.rule in handle.read():
            print("Rule already exists, updating expiration time")
            handle.close()
            handle = open(rules_file, "r")
            tmpfile= open(tmp_rules_file, "w")
            for line in handle.readlines():
                if args.rule in line:
                    tmpfile.write(str(timestamp) + ' ' + args.rule)
                    tmpfile.write("\n")
                else:
                    tmpfile.write(line)
            tmpfile.close()
            handle.close()
            move(tmp_rules_file, rules_file)
            exit(0)
        handle.close()
        try:
            handle = open(rules_file, 'a')
            handle.write(str(timestamp) + ' ' + args.rule)
            handle.write("\n")
            handle.close()
        except IOError:
            raise Exception("unable to write to the rules file: " + rules_file)
        try:
            ufw_insert(args.position, args.rule)
        except CalledProcessError as error:
            if error.output == b"ERROR: Invalid position '1'\n":
                # ufw_insert("",args.rule)
                check_output("ufw " + args.rule, stderr=STDOUT, shell=True)
            else:
                raise Exception("ufw: " + error.output.decode(encoding='UTF-8'))


def ufw_insert(position, rule):
    command = 'ufw insert ' + str(position) + ' ' + rule
    if dry_run:
        print(command)
        return
    check_output(command, stderr=STDOUT, shell=True)


def ufw_delete(rule):
    command = 'ufw delete ' + rule
    if dry_run:
        print(command)
        return
    check_output(command, stderr=STDOUT, shell=True)


def ufw_error(error):
    raise Exception("ufw: " + error.output.decode(encoding='UTF-8'))


if __name__ == '__main__':
    main()
