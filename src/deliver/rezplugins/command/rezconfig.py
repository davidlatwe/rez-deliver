
import os as __os
__root = __os.path.join(__os.path.dirname(__file__), *[".."] * 4)


# CONFIG
deliver = {
    "dev_repository_roots": [
        __os.path.join(__root, "test", "packages"),
        __os.path.join(__root, "test", "others"),
    ],
}
