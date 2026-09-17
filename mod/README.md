# gameassistant Fabric mod

Streams the player's own state (position, biome, inventory, vitals, ...) from
Minecraft to `player_ingest.py` over a local WebSocket, so the assistant's
Player DB stays up to date while you play. Client-side only, no gameplay
changes.

- Minecraft: 26.2
- Fabric Loader: 0.19.5 (see `gradle.properties` for the exact pinned versions)
- **Java 25 required** to compile and run the game itself.
- Mappings: none declared - Mojang's official mappings are used by default as
  of Minecraft 26.1+ (Yarn is discontinued for these versions).

## Building

```
./gradlew.bat build
```

Output jar: `build/libs/gameassistant-<version>.jar` (plus a `-sources.jar`).
Install it into a normal Fabric-loader `mods/` folder to run it in the real
game.

### "Releaseversion 25 nicht unterstützt" / "release version 25 not supported"

This means Gradle's daemon JVM is older than 25 - Loom itself only needs JVM
21+ to load as a plugin, but compiling *this* project targets Java 25, so the
actual compile step needs a JDK 25 daemon.

Check what Gradle is actually using:

```
./gradlew.bat --version
```

Look at the `Daemon JVM:` line. If it's not 25, your `JAVA_HOME` points at an
older JDK. Two ways to fix it:

1. **Scoped to Gradle only (recommended)** - don't touch the system-wide
   `JAVA_HOME` (other tools on the machine may depend on it staying put).
   Instead add this to your **user-level** Gradle properties file at
   `~/.gradle/gradle.properties` (create it if it doesn't exist - this file
   is per-machine and not part of the repo):

   ```
   org.gradle.java.home=C:/Program Files/Java/jdk-25.0.4.1
   ```

   Adjust the path to wherever JDK 25 is actually installed on that machine.

2. **Global fix** - change the `JAVA_HOME` environment variable itself to
   point at the JDK 25 install. Simpler, but affects every Java tool on the
   machine, not just this project.

Oracle JDK 25 is free to install and use, including commercially, under the
NFTC (No-Fee Terms and Conditions), with free updates until September 2028.

### "Dependency requires at least JVM runtime version 21"

This is a different, earlier failure: Loom 1.17 itself can't even load as a
Gradle plugin on a JVM older than 21 (this is separate from, and happens
before, the Java-25-for-compiling requirement above). Install any JDK >= 21
and make sure Gradle's daemon JVM resolves to it (see the `--version` check
above) before worrying about the Java 25 requirement.

## Debugging in-game

The mod runs inside a real dev instance of Minecraft, launched by Loom's
`runClient` task. To attach a debugger to it:

```
./gradlew.bat runClient --debug-jvm
```

`--debug-jvm` is a standard Gradle flag: it starts the launched JVM
*suspended*, listening for a debugger on port `5005` (JDWP). The game window
will not appear until something attaches.

From VS Code (with the Java Extension Pack installed), add a "Attach"
launch config targeting `localhost:5005`, run it after starting the command
above, and set breakpoints directly in the mod's source (e.g.
`GameAssistantModClient.java`). You can then step through the code and
inspect real objects - e.g. the `Holder<Biome>` returned by
`getBiomeManager().getBiome(...)`, or the player's live position - while the
dev game instance is actually running.

## How data actually gets sent

Not HTTP/REST - the mod opens a single persistent WebSocket connection to
`player_ingest.py` (`ws://127.0.0.1:25585`) once, in `connect()`, and keeps
reusing it. Each event (e.g. a position tick) is pushed as one WebSocket text
frame on that existing connection:

```java
socket.sendText(json, true);
```

Example payload for a position event:

```json
{"kind":"position","dim":"minecraft:overworld","pos":[123.456,64.0,-78.9],"biome":"minecraft:plains"}
```

`player_ingest.py` reads frames off that same connection in a loop
(`async for message in websocket:`), parses each as JSON, and dispatches on
`"kind"` to the matching `player_db.write_*` function.

## Finding real, version-matched API signatures

Yarn mappings don't exist for 26.1+, and web search results mix
Yarn/Forge/NeoForge-era method names that don't necessarily match the current
official mappings - this has produced wrong guesses before. The reliable
source is the actual deobfuscated game jar that Loom already downloaded for
this project:

```
~/.gradle/caches/fabric-loom/minecraftMaven/net/minecraft/minecraft-merged-deobf/26.2/minecraft-merged-deobf-26.2.jar
```

Extract a class of interest and inspect it with `javap -p` (from a JDK 25
install, e.g. `C:\Program Files\Java\jdk-25.0.4.1\bin\javap.exe`):

```
unzip -o minecraft-merged-deobf-26.2.jar "net/minecraft/world/level/Level.class" -d /tmp/mcjar
javap -p /tmp/mcjar/net/minecraft/world/level/Level.class
```

This is how the biome lookup (`Level#getBiomeManager()` ->
`BiomeManager#getBiome(BlockPos)` -> `Holder<Biome>`) and the
`ResourceKey#identifier()` rename were confirmed - directly against the real
26.2 jar, not guessed from mixed-version search results.
