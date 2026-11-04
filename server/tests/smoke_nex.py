"""Smoke test for the DQMJ3P NEX server running in DEV mode.

Fake 3DS clients (NintendoClients, 3DS settings, NEX 3.10.1, access key 5812c478) replay the
game's two battle flows:
  friend battle: A CreateMatchmakeSession (gameMode 5, attribs[0]=host id, friends only), B Browse +
                JoinMatchmakeSessionEx (A and B are not friends: the server has no friend list)
  random battle: A and B AutoMatchmakeWithSearchCriteria_Postpone (gameMode 2, two criteria) -> same gathering
then GetSessionURLs, which Pia needs to connect the peers. Then communities (create, join with
password, update) and G-Cup replays (DataStore post + HTTP upload, search, get + HTTP download,
update, delete).

usage: python smoke_nex.py [host] [auth_port] [dev_password]
"""
import random
import sys
import urllib.error
import urllib.request

import anyio
from nintendo.nex import backend, common, datastore, matchmaking, secure, settings

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 45000
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "devpassword"
ACCESS_KEY = "5812c478"
NEX_VERSION = 31001  # 3.10.1
# Values from re/notes/nex_usage.md (DQMJ3P v1.3)
FRIEND_GAME_MODE = 5  # friend battle: attribs[0] = host ID, matched by equality
RANDOM_GAME_MODE = 2  # random battle, single (3 = double): attribs[0] = strength score


_original_criteria_save = matchmaking.MatchmakeSessionSearchCriteria.save


def _criteria_save_310(self, stream, version):
    """NintendoClients stops at NEX 3.5 fields; 3.10 clients also send these (see nex-protocols-go).
    Patched on the class itself because NintendoClients gives every subclass level its own header."""
    _original_criteria_save(self, stream, version)
    stream.u8(0)  # 3.6 MatchmakeParam: structure header version
    stream.u32(4)  # structure header content length
    stream.u32(0)  # empty Map<String, Variant>
    stream.bool(False)  # 3.7 ExcludeUserPasswordSet
    stream.bool(False)  # 3.7 ExcludeSystemPasswordSet
    stream.u32(0)  # 3.8 ReferGID


matchmaking.MatchmakeSessionSearchCriteria.save = _criteria_save_310


def make_settings():
    s = settings.load("3ds")
    s.configure(ACCESS_KEY, NEX_VERSION)
    s["nex.struct_header"] = 1  # NEX >= 3.5 clients send structure headers
    return s


def criteria(game_mode, attrib0="", friends_only=False):
    c = matchmaking.MatchmakeSessionSearchCriteria()
    c.attribs = [attrib0, "", "", "", "", ""]
    c.game_mode = str(game_mode)
    c.min_participants = ""
    c.max_participants = "2"
    # the game fills it from the same flag as the session (nex_st5_MMExt_BrowseMatchmakeSession, +0xae)
    c.matchmake_system = "2" if friends_only else "1"
    c.vacant_only = True
    c.exclude_locked = True
    c.exclude_non_host_pid = True
    c.selection_method = 0
    c.vacant_participants = 1
    return c


def new_session(game_mode, attrib0, friends_only=False):
    session = matchmaking.MatchmakeSession()
    session.game_mode = game_mode
    session.min_participants = 1
    session.max_participants = 2
    # like FUN_0014f51c: flag 1 = anybody (policy 95), flag 2 = friends only (policy 98)
    session.matchmake_system = 2 if friends_only else 1
    session.participation_policy = 98 if friends_only else 95
    session.attribs = [attrib0, 0, 0, 0, 0, 0]
    session.open_participation = True
    session.application_buffer = bytes(256)
    return session


async def logged_in(pid, body):
    async with backend.connect(make_settings(), HOST, PORT) as be:
        async with be.login(str(pid), PASSWORD) as client:
            # like the console: register our (fake) Pia station URL right after login
            url = common.StationURL("prudp", address="127.0.0.1", port=40000 + pid % 1000,
                                    sid=15, type=2, natm=0, natf=0, upnp=0, pmp=0)
            await secure.SecureConnectionClient(client).register([url])
            await body(client)


async def friend_battle():
    created, done = anyio.Event(), anyio.Event()
    host_pid = random.randint(100000, 900000)  # fresh PIDs: stale connections of old runs linger
    guest_pid = host_pid + 1
    gid = {}

    async def host(client):
        mm = matchmaking.MatchmakeExtensionClient(client)
        result = await mm.create_matchmake_session(new_session(FRIEND_GAME_MODE, host_pid, friends_only=True), "", 1)
        gid["value"] = result.gid
        print(f"[friend] host {host_pid} created gathering {result.gid}")
        created.set()
        await done.wait()

    async def guest(client):
        await created.wait()
        mm = matchmaking.MatchmakeExtensionClient(client)
        sessions = await mm.browse_matchmake_session(criteria(FRIEND_GAME_MODE, str(host_pid), friends_only=True), common.ResultRange(0, 100))
        assert [s.id for s in sessions] == [gid["value"]], f"browse returned {[s.id for s in sessions]}"
        await mm.join_matchmake_session_ex(sessions[0].id, "", False, 1)
        urls = await matchmaking.MatchMakingClient(client).get_session_urls(sessions[0].id)
        assert urls, "no session URLs"
        print(f"[friend] guest {guest_pid} joined {sessions[0].id}, host URLs: {[str(u) for u in urls]}")
        done.set()

    async with anyio.create_task_group() as tg:
        tg.start_soon(logged_in, host_pid, host)
        tg.start_soon(logged_in, guest_pid, guest)


async def random_battle():
    first_done, both_done = anyio.Event(), anyio.Event()
    gids = {}

    def player(pid, strength, wait_for=None):
        async def body(client):
            if wait_for:
                await wait_for.wait()
            mm = matchmaking.MatchmakeExtensionClient(client)
            # the game sends two criteria: a narrow and a wide strength range
            crit = [criteria(RANDOM_GAME_MODE, f"{strength - 50},{strength + 50}"),
                    criteria(RANDOM_GAME_MODE, f"{strength - 500},{strength + 500}")]
            gathering = await mm.auto_matchmake_with_search_criteria_postpone(
                crit, new_session(RANDOM_GAME_MODE, strength), "PiaInet Automatch")
            gids[pid] = gathering.id
            print(f"[random] {pid} (strength {strength}) -> gathering {gathering.id}")
            if wait_for is None:
                first_done.set()
                await both_done.wait()
            else:
                urls = await matchmaking.MatchMakingClient(client).get_session_urls(gathering.id)
                assert urls, "no session URLs"
                both_done.set()
        return body

    async with anyio.create_task_group() as tg:
        a = random.randint(100000, 900000)
        tg.start_soon(logged_in, a, player(a, 1000))
        tg.start_soon(logged_in, a + 1, player(a + 1, 1200, first_done))
    assert len(set(gids.values())) == 1, f"players were not matched: {gids}"


async def communities():
    created, joined = anyio.Event(), anyio.Event()
    owner_pid = random.randint(100000, 900000)
    member_pid = owner_pid + 1
    gid = {}

    def community(description):
        c = matchmaking.PersistentGathering()
        c.id = gid.get("value", 0)
        c.owner = owner_pid
        c.host = owner_pid
        c.min_participants = 1
        c.max_participants = 100
        c.participation_policy = 98
        c.policy_argument = 0
        c.flags = 0
        c.state = 0
        c.description = description
        c.type = 1
        c.password = "pw"
        c.attribs = [0, 0, 0, 0, 0, 0]
        c.application_buffer = bytes(0x1b0)  # DQMJ3P community buffer size
        c.participation_start = common.DateTime(0)
        c.participation_end = common.DateTime(0)
        c.matchmake_session_count = 0
        c.num_participants = 0
        return c

    async def owner(client):
        mm = matchmaking.MatchmakeExtensionClient(client)
        gid["value"] = await mm.create_community(community("smoke community"), "")
        print(f"[community] owner {owner_pid} created community {gid['value']}")
        created.set()
        await joined.wait()
        await mm.update_community(community("renamed community"))
        found = await mm.find_community_by_gathering_id([gid["value"]])
        assert found[0].description == "renamed community", found[0].description
        print("[community] owner updated the description")

    async def member(client):
        await created.wait()
        mm = matchmaking.MatchmakeExtensionClient(client)
        found = await mm.find_community_by_gathering_id([gid["value"]])
        assert len(found) == 1 and found[0].password == "", "community not found or password leaked"
        try:
            await mm.join_community(gid["value"], "", "wrong")
            raise AssertionError("joined with a wrong password")
        except common.RMCError as e:
            print(f"[community] wrong password refused: {e}")
        await mm.join_community(gid["value"], "", "pw")
        mine = await mm.find_community_by_participant(member_pid, common.ResultRange(0, 10))
        assert gid["value"] in [c.id for c in mine], "membership not recorded"
        try:
            await mm.update_community(community("hijacked"))
            raise AssertionError("non-owner updated the community")
        except common.RMCError as e:
            print(f"[community] member {member_pid} joined; non-owner update refused: {e}")
        joined.set()

    async with anyio.create_task_group() as tg:
        tg.start_soon(logged_in, owner_pid, owner)
        tg.start_soon(logged_in, member_pid, member)


async def replays():
    """G-Cup replay flow: PreparePostObject + HTTP POST + CompletePostObject, then another player
    SearchObject (by owner) + PrepareGetObject + HTTP GET, then PrepareUpdateObject + DeleteObject."""
    owner_pid = random.randint(100000, 900000)
    replay = bytes(random.getrandbits(8) for _ in range(300))
    found = {}

    def http(method, url, body=b"", content_type="application/octet-stream"):
        request = urllib.request.Request(url, data=body if method == "POST" else None, method=method,
                                         headers={"Content-Type": content_type})
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read()

    def multipart(fields, data):
        boundary = "dqmj3pboundary"
        out = b""
        for key, value in fields:
            out += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="file"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        return out, f"multipart/form-data; boundary={boundary}"

    async def owner(client):
        store = datastore.DataStoreClient(client)
        param = datastore.DataStorePreparePostParam()
        param.size = len(replay)
        param.name = "replay"
        param.data_type = 7
        param.meta_binary = b"meta"
        param.flag = 0
        param.period = 90
        param.extra_data = []
        param.persistence_init_param.persistence_id = 0
        info = await store.prepare_post_object(param)
        body, content_type = multipart([(f.key, f.value) for f in info.form], replay)
        for url in (info.url.rsplit("/", 1)[0] + "/" + "0" * 32, info.url.rsplit("/", 1)[0]):
            try:
                await anyio.to_thread.run_sync(http, "POST", url, body, content_type)
            except urllib.error.HTTPError as e:
                assert e.code in (400, 403), e
            else:
                raise AssertionError(f"upload accepted without the token: {url}")
        print("[replay] uploads without the token refused")
        await anyio.to_thread.run_sync(http, "POST", info.url, body, content_type)
        complete = datastore.DataStoreCompletePostParam()
        complete.data_id = info.data_id
        complete.success = True
        await store.complete_post_object(complete)
        found["data_id"] = info.data_id
        print(f"[replay] {owner_pid} posted object {info.data_id} ({len(replay)} B)")

    async def viewer(client):
        store = datastore.DataStoreClient(client)
        search = datastore.DataStoreSearchParam()
        search.search_target = 1
        search.owner_ids = [owner_pid]
        search.data_type = 7
        search.result_range.size = 10
        search.result_option = 4
        result = await store.search_object(search)
        assert [m.data_id for m in result.result] == [found["data_id"]], result.result
        assert result.result[0].meta_binary == b"meta"
        get = datastore.DataStorePrepareGetParam()
        get.data_id = found["data_id"]
        info = await store.prepare_get_object(get)
        data = await anyio.to_thread.run_sync(http, "GET", info.url)
        assert data == replay and info.size == len(replay)
        print(f"[replay] viewer downloaded object {found['data_id']} from {info.url}")

    async def cleanup(client):
        store = datastore.DataStoreClient(client)
        update = datastore.DataStorePrepareUpdateParam()
        update.data_id = found["data_id"]
        update.size = len(replay)
        update.update_password = 0
        update.extra_data = []
        info = await store.prepare_update_object(update)
        assert info.version == 1
        delete = datastore.DataStoreDeleteParam()
        delete.data_id = found["data_id"]
        delete.update_password = 0
        await store.delete_object(delete)
        print("[replay] update prepared (version 1), object deleted")

    await logged_in(owner_pid, owner)
    await logged_in(owner_pid + 1, viewer)
    await logged_in(owner_pid, cleanup)


async def main():
    with anyio.fail_after(60):
        await friend_battle()
        await random_battle()
        await communities()
        await replays()
    print("SMOKE TEST OK")


anyio.run(main)
