set appPath to POSIX path of (path to me)
set projectDir to do shell script "dirname " & quoted form of appPath
set startScript to projectDir & "/start.sh"
set logFile to projectDir & "/app-launch.log"
do shell script "bash " & quoted form of startScript & " >> " & quoted form of logFile & " 2>&1 &"