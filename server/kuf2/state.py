"""Persistent server state: one JSON file (accounts, characters). Single local player, so no locking."""
import json, os, pathlib

DB = pathlib.Path(__file__).resolve().parents[1] / "data" / "db.json"


class State:
    def __init__(self, path=DB):
        self.path = path
        self.db = json.loads(path.read_text()) if path.exists() else {"accounts": {}, "next_id": 1}
        self.world_keys = {}
        self.game_sessions = {}     # account id -> its live game session (world requests that act in a battle room)
        self.world_sessions = {}    # account id -> its world session (a room that sends the client on to another
        #                             room: world.continue_mission, Sortie I into Sortie II)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.db, indent=1))
        tmp.replace(self.path)

    def issue_world_key(self, acct):
        """One-time key the client carries from the login role to the world role (0x1007 u64)."""
        key = int.from_bytes(os.urandom(8), "little") >> 1
        self.world_keys[key] = acct
        return key

    def create_character(self, acct, name, cls, look_hex):
        c = {"id": self.db.setdefault("next_char_id", 1), "name": name, "class": cls, "look": look_hex, "level": 1}
        self.db["next_char_id"] = c["id"] + 1
        acct["characters"].append(c)
        self.save()
        return c

    def account_by_id(self, acct_id):
        for acct in self.db["accounts"].values():
            if acct["id"] == acct_id:
                return acct
        raise KeyError(f"no account {acct_id}")

    def char_by_id(self, char_id):
        """(account, character) of a character id: what the game login (0x5084) names (live 2026-09-30: a second
        character's id matched no account)."""
        for acct in self.db["accounts"].values():
            for c in acct["characters"]:
                if c["id"] == char_id:
                    return acct, c
        raise KeyError(f"no character {char_id}")

    def account_for_steam(self, steam_id, persona):
        key = str(steam_id)
        acct = self.db["accounts"].get(key)
        if acct is None:
            acct = {"id": self.db["next_id"], "name": persona or f"player{self.db['next_id']}", "characters": []}
            self.db["accounts"][key] = acct
            self.db["next_id"] += 1
            self.save()
        return acct
