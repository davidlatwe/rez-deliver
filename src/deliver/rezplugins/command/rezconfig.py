

def on_package_deployed_callback(name, path):
    print("\nPackage %s deployed to -> %s\n" % (name, path))


# CONFIG
deliver = {
    "dev_repository_roots": [
        # you're developer package repository here.
    ],

    "on_package_deployed_callback": on_package_deployed_callback,

    "max_git_tag_from_remote": 10,

}
