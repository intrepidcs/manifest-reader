#!/bin/bash
# Found here https://stackoverflow.com/questions/4774054/reliable-way-for-a-bash-script-to-get-the-full-path-to-itself
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

case "$(uname -s)" in
  CYGWIN*)
    echo "detected cygwin!"
    export DIR=`cygpath $DIR -w`
    ;;
esac

unameOut="$(uname -s)"
case "${unameOut}" in
    Linux*)     machine=Linux;;
    Darwin*)    machine=Mac;;
    CYGWIN*)    machine=Cygwin;;
    MINGW*)     machine=MinGw;;
    *)          machine="UNKNOWN:${unameOut}"
esac
if [ $machine == "Linux" ]; then
  PYTHON="python3"
else
  PYTHON="python"
fi

vstyle () {
  args="$@"
  if [ -z ${VSG_ADDITIONAL_CONFIG+x} ]; then
    additional_config=""
  else
    additional_config="$VSG_ADDITIONAL_CONFIG"
  fi
  $PYTHON $BASE_DIR/submodules/manifest-reader/vsg_util.py "$additional_config" --run --vsg-args="$args"
}

export PYTHONPATH="${DIR}"
export PATH="${DIR}/bin:${PATH}"
export PATH="$PATH:${DIR}/runnable"
