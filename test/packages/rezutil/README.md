
A package build tool stole from https://github.com/mottosso/rez-for-projects

### Usage

```python
# in package.py
private_build_requires = ["rezutil-1"]
build_command = "python -m rezutil build {root}"
```

### Work with `rez-pipz`

```python
# in package.py
private_build_requires = ["rezutil-1", "pipz"]
build_command = "python -m rezutil build {root} --use-pipz"
```

Why ?

Rez packages (in filesystem based repository) are case sensitivity, but packages in PyPI are not, which may cause the dependency names that parsed from `pipz` in package `requires` have different letter case from what actually been installed.

For example, `rich` has a dependency package called `Pygments`, but the name in `rich`'s `requires` list is `pygments`.

*Also see https://github.com/mottosso/rez-pipz/issues/30.*

To workaround this, I find explicitly define all `pipz` installed packages into each `package.py` helps. Because in that way, not only packages name and the requires are explicitly defined (letter case being handled) but also you can manage them all with other packages that are not installed by `pipz` in the same manner.

Here my current workflow:

1. Download the package into some other place with `--prefix`

    ```bash
    $ rez-env pipz -- install rich --prefix ~/test
    ```

2. Find out what package will be installed in which version and requires.

3. Write `package.py` for each of them.

4. `rez-build` them in the order they need.

TODO:
maybe we could use, for example, `johnnydep pysftp --output-format json`
to generate `package.py` or auto-deploy list.
