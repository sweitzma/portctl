import hashlib
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from typing import Optional

import click

TABLE_PATH = Path("/tmp/.portctl.db")
TABLE_NAME = "forwards"
SCHEMA = {
    "remote_host": "text",
    "remote_ip": "text",
    "remote_port": "int",
    "local_ip": "text",
    "local_port": "int",
    "pid": "int",
    "start_time": "int",
    "description": "text",
}


@dataclass
class PortForward:
    remote_host: str
    remote_ip: str
    remote_port: int
    local_ip: str
    local_port: int
    pid: int
    start_time: Optional[int] = None
    description: Optional[str] = None

    @classmethod
    def from_ps_aux_output(cls, output: str):
        parts = output.split()
        pid = parts[1]
        mapping = parts[-2]
        host = parts[-1]
        local_ip, local_port, remote_ip, remote_port = mapping.split(":")
        return cls(
            host, remote_ip, int(remote_port), local_ip, int(local_port), int(pid)
        )

    @classmethod
    def from_sqlite_ouput(cls, output: str):
        pass

    def to_sql_insert(self):
        lookup = asdict(self)
        values = []
        for col, kind in SCHEMA.items():
            value = lookup[col]
            if value is None:
                values.append("NULL")
            elif kind == "text":
                values.append(f"'{value}'")
            elif kind == "int":
                values.append(str(value))
            else:
                raise "Do not know how to insert this."

        columns = [f"{name}" for name, kind in SCHEMA.items()]
        return f"INSERT INTO {TABLE_NAME} ({','.join(columns)})\nVALUES ({','.join(values)});"

    def unsafe_insert(self):
        """
        Will create duplicate rows.
        """
        con = sqlite3.connect(TABLE_PATH)
        cur = con.cursor()
        cur.execute(self.to_sql_insert())
        con.commit()
        con.close()

    @property
    def id(self):
        id_str = f"{self.remote_host}{self.remote_ip}{self.remote_port}"
        id_str += f"{self.local_ip}{self.local_port}"
        return hashlib.sha256(id_str.encode()).hexdigest()

    def merge(self, other):
        s = {k: v for k, v in asdict(self).items() if v is not None}
        o = {k: v for k, v in asdict(other).items() if v is not None}
        fields = s | o
        return PortForward(**fields)

    def kill(self):
        subprocess.Popen(["kill", "-15", str(self.pid)], stdout=subprocess.PIPE)

    def open(self):
        mapping = (
            f"{self.local_ip}:{self.local_port}:{self.remote_ip}:{self.remote_port}"
        )
        subprocess.Popen(
            ["ssh", "-N", "-f", "-L", mapping, self.remote_host], stdout=subprocess.PIPE
        )


def ensure_table_exists():
    columns = [f"{name} {kind}" for name, kind in SCHEMA.items()]
    column_sql = ",".join(columns)

    con = sqlite3.connect(TABLE_PATH)
    cur = con.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} ({column_sql});
        """
    )
    con.commit()
    con.close()


def update_entries():
    ps_rows = ps_entries()
    sqlite_rows = sqlite_entries()

    # only keep active forwards but update with DB data
    entries = {pf.id: pf for pf in ps_rows}
    for pf in sqlite_rows:
        if pf.id in entries:
            entries[pf.id] = entries[pf.id].merge(pf)

    drop_rows_and_repopulate(entries.values())


def ps_entries():
    ps = subprocess.Popen(["ps", "aux"], stdout=subprocess.PIPE)
    grep = subprocess.Popen(
        ["grep", "[s][s][h] -N -f -L"], stdout=subprocess.PIPE, stdin=ps.stdout
    )
    ps.stdout.close()
    res = grep.communicate()[0]
    res = res.decode("utf-8")

    entries = []
    for line in res.split("\n"):
        if len(line) < 3:
            continue

        entries.append(PortForward.from_ps_aux_output(line))

    return entries


def sqlite_entries():
    con = sqlite3.connect(TABLE_PATH)
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT * FROM {TABLE_NAME};
        """
    )
    rows = cur.fetchall()
    return [PortForward(*r) for r in rows]


def drop_rows_and_repopulate(rows):
    con = sqlite3.connect(TABLE_PATH)
    cur = con.cursor()
    cur.execute(f"DELETE FROM {TABLE_NAME};")
    con.commit()
    con.close()

    for row in rows:
        row.unsafe_insert()


def duration_to_str(duration: int) -> str:
    if duration < 120:
        return f"{duration}s"
    elif duration < 3600:
        mins = duration // 60
        return f"{mins}m"
    elif duration < 86_400:
        hours = duration // 3600
        return f"{hours}h"
    else:
        days = duration // 86_400
        return f"{days}d"


@click.group()
def cli():
    pass


@cli.command()
@click.argument("cols", nargs=-1)
def ls(cols):
    """
    View active port forwarding sessions
    """
    pfs = sqlite_entries()

    # format: { id: [<title>, <row val fn>, <formatting>] }
    columns = {
        "id": ["ID", lambda pf: pf.id[:4], "{:8}"],
        "pid": ["PID", lambda pf: str(pf.pid), "{:8}"],
        "host": ["HOST", lambda pf: pf.remote_host, "{:8}"],
        "mapping": [
            "MAPPING",
            lambda pf: f"{pf.remote_port}->{pf.local_port}",
            "{:16}",
        ],
        "time": [
            "TIME",
            lambda pf: duration_to_str(int(time()) - pf.start_time),
            "{:8}",
        ],
        "desc": ["DESC", lambda pf: pf.description, "{}"],
    }

    # choose columns to show based on optional arguments
    if len(cols) == 0:
        cols = ["id", "host", "mapping", "time", "desc"]  # default columns
    else:
        valid_cols = list(set(cols) & set(columns.keys()))
        cols = sorted(valid_cols, key=lambda c: cols.index(c))

    print("".join([columns[col][2].format(columns[col][0]) for col in cols]))
    for pf in pfs:
        print("".join([columns[col][2].format(columns[col][1](pf)) for col in cols]))


@cli.command()
@click.argument("ids", nargs=-1)
@click.option("-a", "--all", help="kill all open port forwards", is_flag=True)
def kill(ids, all):
    """
    Kill a port forwarding process
    """
    pfs = sqlite_entries()
    id_to_pf = {pf.id: pf for pf in pfs}
    existing_ids = id_to_pf.keys()

    if all:
        ids = existing_ids
    elif len(ids) == 0:
        click.echo(
            "Error: must provide one of <IDS> or <OPTIONS>. See help via `portctl kill --help`"
        )

    for id in ids:
        n = len(id)
        match = [eid for eid in existing_ids if eid[:n] == id]
        if len(match) == 0:
            print("no process for id", id)
        elif len(match) > 1:
            print("no unuqie match for id", id)
        else:
            print(f"killing {match[0][:6]}")
            id_to_pf[match[0]].kill()


@cli.command()
@click.option("--host", default="fjord", help="remote host, default=fjord")
@click.option("--host-ip", default="localhost", help="remote ip, default=localhost")
@click.argument("host-port", type=int, required=True)
@click.option("--local-ip", default="localhost", help="local ip, default=localhost")
@click.argument("local-port", type=int, required=False)
@click.option("-d", "--desc", help="description")
def new(host, host_ip, host_port, local_ip, local_port, desc):
    """
    Create a new port forwarding session in the background
    """
    if local_port is None:
        local_port = host_port

    pf = PortForward(
        host,
        host_ip,
        host_port,
        local_ip,
        local_port,
        None,  # PID unknown
        int(time()),
        desc,
    )
    pf.unsafe_insert()
    pf.open()


@cli.command()
@click.argument("ids", nargs=-1, required=True)
def link(ids):
    """
    Print out local http url associated with the port forward
    """
    pfs = sqlite_entries()
    id_to_pf = {pf.id: pf for pf in pfs}
    existing_ids = id_to_pf.keys()

    for id in ids:
        n = len(id)
        match = [eid for eid in existing_ids if eid[:n] == id]
        if len(match) == 0:
            print("no process for id", id)
        elif len(match) > 1:
            print("no unuqie match for id", id)
        else:
            pf = id_to_pf[match[0]]
            print(f"http://{pf.local_ip}:{pf.local_port}")


if __name__ == "__main__":
    ensure_table_exists()
    update_entries()
    cli()
