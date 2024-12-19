#!/bin/bash
PID="$(pidof wvkbd-mobintl)"
if [ "$PID" != "" ]; then
    kill $PID
else
    wvkbd-mobintl &
fi