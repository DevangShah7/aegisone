@echo off
REM Wrapper that invokes the locally cached Gradle 8.14.3 with JDK 25 on PATH.
setlocal
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"
set "GRADLE_HOME=C:\Users\DEVANG\.gradle\wrapper\dists\gradle-8.14.3-all\10utluxaxniiv4wxiphsi49nj\gradle-8.14.3"
"%GRADLE_HOME%\bin\gradle.bat" %*
