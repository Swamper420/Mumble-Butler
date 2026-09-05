"""Backend factory: selects Mumble vs TeamSpeak 6 via config.USE_TEAMSPEAK."""
import config


def create_backend(bot):
    """Return a VoiceBackend instance based on config.USE_TEAMSPEAK.

    - False (default) -> MumbleBackend (pymumble).
    - True            -> TeamspeakBackend (SSH query + voice bridge).
    """
    use_ts = getattr(config, "USE_TEAMSPEAK", False)
    if use_ts:
        from backends.teamspeak_backend import TeamspeakBackend
        return TeamspeakBackend(bot)
    from backends.mumble_backend import MumbleBackend
    return MumbleBackend(bot)
