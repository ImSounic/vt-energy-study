#!/usr/bin/env bash
# JVM wrapper for the Mac BACKGROUND arm: JMH's -jvm option runs each forked
# benchmark JVM through this script, which starts it in the background QoS
# class (taskpolicy -b), confining it to the E cores.
exec taskpolicy -b "${JAVA_HOME:?JAVA_HOME must be set}/bin/java" "$@"
