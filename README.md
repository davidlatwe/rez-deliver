# rez-deliver

Rez command line tool for deploying packages.

### Environment Variables

* REZ_DELIVER_PKG_PAYLOAD_VER


### Package Types

* version per dir
* version per git tag

* payload included
* payload separated
    - From git (source)
    - From archive (prebuilt binaries)
* payload existed
    - bind
    - reference


We may not know what variant/tool the package have if the package definition file is versioning by git.


### Package Version Specification

`<pacakge payload version>-<pacakge definition version>`

E.g. `0.1.0-p1`
