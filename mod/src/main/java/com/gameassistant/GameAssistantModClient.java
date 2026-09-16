package com.gameassistant;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.Locale;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * First real slice of the bridge to player_ingest.py: connects out to it
 * (Python hosts the WebSocket server, not the mod - see player_ingest.py's
 * own module docstring for why) and streams the player's position on a
 * timer. Everything else (inventory, equipment, effects, vitals, deaths,
 * ...) follows the same shape once this is confirmed working end to end -
 * not built yet, deliberately, so there's one small, testable thing to
 * validate before extending it.
 */
public class GameAssistantModClient implements ClientModInitializer {
	public static final String MOD_ID = "gameassistant";
	public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

	private static final URI INGEST_URI = URI.create("ws://127.0.0.1:25585");

	// Once per second, not every tick (20/s) - player_db.py's own design
	// notes call out 20Hz position pushes as wasteful precision for voice
	// Q&A; this matches that, not just an arbitrary choice.
	private static final int POSITION_INTERVAL_TICKS = 20;

	// Held as a field, not a local in connect() - a WebSocket's underlying
	// connection depends on the HttpClient that created it staying alive.
	// An unreferenced local goes out of scope the moment connect() returns
	// and becomes eligible for GC; once collected, its connection-managing
	// resources can be torn down out from under the WebSocket we're still
	// holding in `socket`, killing the connection with a raw reset - no
	// close frame, because nothing on our side asked for one. Confirmed
	// this was the actual cause of a real connection-reset-shortly-after
	// -connecting failure, not just a theoretical concern.
	private HttpClient httpClient;
	private WebSocket socket;
	private int tickCounter = 0;

	@Override
	public void onInitializeClient() {
		connect();
		ClientTickEvents.END_CLIENT_TICK.register(this::onEndClientTick);
	}

	private void connect() {
		httpClient = HttpClient.newHttpClient();
		httpClient.newWebSocketBuilder()
				.buildAsync(INGEST_URI, new IngestListener())
				.whenComplete((webSocket, error) -> {
					if (error != null) {
						// Not fatal - player_ingest.py may just not be running yet.
						// No retry loop here on purpose: this is the first slice,
						// kept deliberately simple until it's confirmed working at
						// all (see class docstring).
						LOGGER.warn("Could not connect to player_ingest.py at {} - is it running? ({})", INGEST_URI, error.toString());
						return;
					}
					socket = webSocket;
					LOGGER.info("Connected to player_ingest.py at {}", INGEST_URI);
				});
	}

	private void onEndClientTick(Minecraft client) {
		if (++tickCounter < POSITION_INTERVAL_TICKS) {
			return;
		}
		tickCounter = 0;

		LocalPlayer player = client.player;
		if (player == null || socket == null) {
			return;
		}

		// Locale.ROOT, not the platform default - a comma-decimal locale
		// would otherwise produce "123,5" here and break the JSON.
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"position\",\"dim\":\"%s\",\"pos\":[%f,%f,%f]}",
				dimensionId(player), player.getX(), player.getY(), player.getZ()
		);
		socket.sendText(json, true);
	}

	private String dimensionId(LocalPlayer player) {
		// ResourceKey#location was renamed to #identifier as part of the
		// ResourceLocation -> Identifier rename in 1.21.11 (confirmed by a
		// real compile failure against this exact line, then verified via
		// search - not guessed twice).
		return player.level().dimension().identifier().toString();
	}

	private static class IngestListener implements WebSocket.Listener {
		@Override
		public void onError(WebSocket webSocket, Throwable error) {
			LOGGER.warn("WebSocket error: {}", error.toString());
		}
	}
}
