"""
Function definition
  Wrapper for the python subprocess module
"""

import logging
import subprocess
from typing import Optional, List, Union


def arm_subprocess(cmd: Union[str, List[str]], shell=False, check=False) -> Optional[str]:
    """
    Spawn blocking subprocess

    :param cmd: Command to run
    :param shell: Run ``cmd`` in a shell
    :param check: Raise ``CalledProcessError`` if ``cmd`` returns non-zero exit code

    :return: Output (both stdout and stderr) of ``cmd``, or ``None`` if it returned a non-zero exit code

    :raise CalledProcessError:
    """
    arm_process = None
    logging.debug(f"Running command: {cmd}")
    try:
        arm_process = subprocess.check_output(
            cmd,
            shell=shell,
            stderr=subprocess.STDOUT,
            encoding="utf-8"
        )
    except (subprocess.CalledProcessError, OSError) as error:
        decoded_output: Optional[str] = None
        if isinstance(error, subprocess.CalledProcessError):
            decoded_output = (error.output or "").strip()
        if not check and _is_expected_umount_idle(cmd, decoded_output):
            logging.debug(f"{cmd}: already unmounted")
            return None
        log_fn = logging.error if check else logging.debug
        log_fn(
            f"Error while running command: {cmd}\n"
            + (
                f"Output was: {decoded_output}"
                if decoded_output
                else "The command produced no output."
            ),
            exc_info=error if check else False,
        )
        if check:
            raise error

    return arm_process


def _is_expected_umount_idle(cmd: Union[str, List[str]], output: Optional[str]) -> bool:
    """True when umount failed only because nothing was mounted."""
    if isinstance(cmd, list):
        name = str(cmd[0]) if cmd else ""
    else:
        name = str(cmd).split()[0] if cmd else ""
    if name.split("/")[-1] != "umount":
        return False
    text = (output or "").lower()
    return "not mounted" in text or "no mount point specified" in text
