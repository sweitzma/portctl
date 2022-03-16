# portctl
This is a CLI utility that helps me manage my port forwarding over SSH.

### Requirements
* `python3`
* python packages: `click`, `pyyaml`
* `sqlite3`

## Usage
See the various `--help` commands for complete usage options. Here is a brief
example of how this can be used.

```bash
# view current port forwarding processes
$ portctl ls
ID      HOST    MAPPING         TIME

# create a new port forwarding background process
# equivalent to: ssh -N -f -L localhost:7788:localhost:8888 <default_host>
$ portctl new 8888 7788 --desc "forward jupyter lab"

# view current port forwarding processes, notice the new addition
$ portctl ls
ID      HOST    MAPPING         TIME
5dc7    fjord   8888->7788      16s

# view current port forwarding processes, here we specify columns to show 
$ portctl ls host mapping desc
HOST    MAPPING         DESC
fjord   8888->7788      forward jupyter lab

# kill the process by ID, alternatively there is a `--all` option
$ portctl kill 5dc7
killing 5dc764

# view current port forwarding processes, notice the one we created then killed is gone
$ portctl ls
ID      HOST    MAPPING         TIME
```

As you can see, `portctl` provides a convenient way to create, monitor, and kill
SSH port forwarding.

## Config file
`portctl` uses a config file located at `~/.config/portctl/config.yml` to
provide some defaults.

This is an example config file
```yml
# set the default host
default_host: fjord

# set some preset port forwards that can be referenced by name, note
# that all of these fields are required
presets:
  - name: data_lab
    description: "Jupyter Lab for data collection"
    local_ip: localhost
    local_port: 8888
    remote_host: fjord
    remote_ip: localhost
    remote_port: 8888
```
