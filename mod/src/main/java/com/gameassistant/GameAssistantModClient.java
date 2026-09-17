package com.gameassistant;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.Locale;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.NonNullList;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.biome.Biome;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Connects to a local player_ingest.py process over WebSocket and pushes the player's
 * information and actions for ingestion into a SQLite database.
 */
public class GameAssistantModClient implements ClientModInitializer {
	public static final String MOD_ID = "gameassistant";
	public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

	private static final URI INGEST_URI = URI.create("ws://127.0.0.1:25585");

	// Once every STATE_PUSH_INTERVAL_TICKS ticks, push data
	// (20 ticks per second, so 100 ticks = 5 seconds)
	private static final int STATE_PUSH_INTERVAL_TICKS = 100;

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
						// TDOD: Consider retrying after a delay, or on the next tick.
						LOGGER.warn("Could not connect to player_ingest.py at {} - is it running? ({})", INGEST_URI, error.toString());
						return;
					}
					socket = webSocket;
					LOGGER.info("Connected to player_ingest.py at {}", INGEST_URI);
				});
	}

	private void onEndClientTick(Minecraft client) {
		// Send player state to the ingest process every STATE_PUSH_INTERVAL_TICKS ticks.
		if (++tickCounter < STATE_PUSH_INTERVAL_TICKS) {
			return;
		}
		tickCounter = 0;

		LocalPlayer player = client.player;
		if (player == null || socket == null) {
			return;
		}

		sendPosition(player);
		sendVitals(client, player);
		sendGameTime(player);
		sendInventory(player);
		sendEquipment(player);
	}

	private void sendPosition(LocalPlayer player) {
		// {"kind":"position","dim":"minecraft:overworld","pos":[123,64,-79],"biome":"minecraft:plains"}
		BlockPos pos = player.blockPosition();
		// Locale.ROOT, not the platform default - a comma-decimal locale
		// would otherwise produce "123,5" here and break the JSON.
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"position\",\"dim\":\"%s\",\"pos\":[%d,%d,%d],\"biome\":\"%s\"}",
				dimensionId(player), pos.getX(), pos.getY(), pos.getZ(), biomeId(player, pos)
		);
		socket.sendText(json, true);
	}

	private void sendVitals(Minecraft client, LocalPlayer player) {
		// {"kind":"vitals","health":19.0,"hunger":20,"saturation":5.0,"xp_level":3,"xp_progress":0.75,"game_mode":"survival"}
		// experienceProgress is a float in [0,1) - round to an int percent for the ingest side.
		int xpProgressPercent = Math.round(player.experienceProgress * 100);
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"vitals\",\"health\":%.1f,\"hunger\":%d,\"saturation\":%f,\"xp_level\":%d,\"xp_progress\":%d,\"game_mode\":\"%s\"}",
				player.getHealth(), player.getFoodData().getFoodLevel(), player.getFoodData().getSaturationLevel(),
				player.experienceLevel, xpProgressPercent, gameModeId(client)
		);
		socket.sendText(json, true);
	}

	private void sendGameTime(LocalPlayer player) {
		// {"kind":"game_time","day_time":14523,"day_count":7}
		// Minecraft 26.2 replaced the old Level#getDayTime()/getGameTime()
		// with a WorldClock/ClockManager system
		long totalTicks = player.level().getOverworldClockTime();
		long dayTime = totalTicks % 24000;
		long dayCount = totalTicks / 24000;
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"game_time\",\"day_time\":%d,\"day_count\":%d}",
				dayTime, dayCount
		);
		socket.sendText(json, true);
	}

	private void sendInventory(LocalPlayer player) {
		// {"kind":"inventory","slots":[{"slot":0,"item":"minecraft:diamond","count":12}, ...]}
		// getNonEquipmentItems() is the 36 hotbar+main slots specifically
		NonNullList<ItemStack> items = player.getInventory().getNonEquipmentItems();
		StringBuilder slots = new StringBuilder();
		for (int slot = 0; slot < items.size(); slot++) {
			ItemStack stack = items.get(slot);
			if (stack.isEmpty()) {
				continue;
			}
			if (!slots.isEmpty()) {
				slots.append(',');
			}
			slots.append(String.format(
					Locale.ROOT,
					"{\"slot\":%d,\"item\":\"%s\",\"count\":%d}",
					slot, itemId(stack), stack.getCount()
			));
		}
		socket.sendText("{\"kind\":\"inventory\",\"slots\":[" + slots + "]}", true);
	}

	private void sendEquipment(LocalPlayer player) {
		// {"kind":"equipment","slots":{"mainhand":"minecraft:diamond_sword","offhand":null,...}}
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"equipment\",\"slots\":{\"mainhand\":%s,\"offhand\":%s,\"head\":%s,\"chest\":%s,\"legs\":%s,\"feet\":%s}}",
				jsonItemId(player, EquipmentSlot.MAINHAND), jsonItemId(player, EquipmentSlot.OFFHAND),
				jsonItemId(player, EquipmentSlot.HEAD), jsonItemId(player, EquipmentSlot.CHEST),
				jsonItemId(player, EquipmentSlot.LEGS), jsonItemId(player, EquipmentSlot.FEET)
		);
		socket.sendText(json, true);
	}

	private String jsonItemId(LocalPlayer player, EquipmentSlot slot) {
		ItemStack stack = player.getItemBySlot(slot);
		return stack.isEmpty() ? "null" : "\"" + itemId(stack) + "\"";
	}

	private String itemId(ItemStack stack) {
		return BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();
	}

	private String dimensionId(LocalPlayer player) {
		// Overworld, Nether or End
		return player.level().dimension().identifier().toString();
	}

	private String biomeId(LocalPlayer player, BlockPos pos) {
		// current biome at the player's location, e.g. "minecraft:plains" or "minecraft:nether_wastes"
		Holder<Biome> biome = player.level().getBiomeManager().getBiome(pos);
		return biome.unwrapKey().map(ResourceKey::identifier).map(Object::toString).orElse("unknown");
	}

	private String gameModeId(Minecraft client) {
		// survival, creative, adventure, spectator, or unknown
		if (client.gameMode == null) {
			return "unknown";
		}
		GameType mode = client.gameMode.getPlayerMode();
		return mode != null ? mode.getSerializedName() : "unknown";
	}

	private static class IngestListener implements WebSocket.Listener {
		@Override
		public void onError(WebSocket webSocket, Throwable error) {
			LOGGER.warn("WebSocket error: {}", error.toString());
		}
	}
}
