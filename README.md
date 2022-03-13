# portctl
This is a CLI utility that helps me manage my port forwarding over SSH.

### Requirements
* `python3`
* python packages: `click`
* `sqlite3`

## Usage
See the various `--help` commands for complete usage options. Here is a brief
example of how this can be used.

```
$ portctl ls
ID      HOST    MAPPING         TIME

$ portctl new 8888 7788 --desc "forward jupyter lab"

$ portctl ls
ID      HOST    MAPPING         TIME
5dc7    fjord   8888->7788      16s

$ portctl ls host mapping desc
HOST    MAPPING         DESC
fjord   8888->7788      forward jupyter lab

$ portctl kill 5dc7
killing 5dc764

$ portctl ls
ID      HOST    MAPPING         TIME
```

As you can see, `portctl` provides a convenient way to create, monitor, and kill
SSH port forwarding.
