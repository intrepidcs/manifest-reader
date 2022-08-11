pushd %~dp0
set script_dir=%CD%
popd
set PYTHONPATH=%script_dir%
set PATH=%PATH%;%script_dir%/runnable
