import os
import json
from pathlib import Path


workPath = Path.home().joinpath("utils")
configFile = Path.home().joinpath("utils", "config.json")


def loadConfigFromFile():
    with open(configFile) as f:
        return json.load(f)


config: dict = loadConfigFromFile()

linkMap: dict = config["link_map"]


def mkSingleLink(srcDir, fileName, linkDir: str):
    srcPath = Path(workPath.joinpath(srcDir, fileName))

    linkName = config[srcDir][fileName]

    linkDir = linkDir.replace("~", Path.home().__str__())

    linkPath = Path(linkDir, linkName)

    if os.path.exists(linkPath):
        os.remove(linkPath)

    if not os.path.exists(srcPath):
        print(srcPath, " is not exist, skip")
        return

    os.symlink(srcPath, linkPath)

    print("make link:", srcPath, " -> ", linkPath)


def install():

    for dir, val in config.items():
        if dir == "link_map":
            continue

        for name, _ in val.items():
            mkSingleLink(dir, name, config["link_map"][dir])


def mkDir():
    for dir in config["link_map"].values():
        try:
            dir = dir.replace("~", Path.home().__str__())
            os.mkdir(dir)
        except FileExistsError:
            pass


if __name__ == "__main__":
    mkDir()
    install()
