package com.gameassistant;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.Collection;
import java.util.Locale;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.fabric.api.client.screen.v1.ScreenEvents;
import net.fabricmc.fabric.api.event.client.player.ClientPlayerBlockBreakEvents;
import net.fabricmc.fabric.api.event.player.UseBlockCallback;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.NonNullList;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.contents.TranslatableContents;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.block.BarrelBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.ChestBlock;
import net.minecraft.world.level.block.ShulkerBoxBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Client-side mod that runs in the Minecraft client and collects player state information.
 * Connects to a local player_ingest.py process over WebSocket and pushes the player's
 * information and actions for ingestion into a SQLite database.
 * 
 * TODOs: visited structures, more containers (furnace, smoker, etc.), ender chest
 * 
 * Information fetched:
 * - Player position, dimension, and biome
 * - Player vitals: health, hunger, saturation, XP level and progress, game mode
 * - Game time: day time and day count
 * - Player inventory: hotbar and main slots
 * - Player equipment: main hand, off hand, armor slots
 * - Active effects: potion effects with ID, amplifier, and duration
 * - Player death events: position, dimension, and cause
 * - Container interactions: chest, barrel, shulker box, etc.
 * - Block placements and breaks: position, dimension, item ID, and action (place/break)
 * - Player respawn point changes: position and dimension
 */
public class GameAssistantModClient implements ClientModInitializer {
	public static final String MOD_ID = "gameassistant";
	public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

	private static final URI INGEST_URI = URI.create("ws://127.0.0.1:25585");

	// Once every STATE_PUSH_INTERVAL_TICKS ticks, push data
	// (20 ticks per second, so 100 ticks = 5 seconds)
	private static final int STATE_PUSH_INTERVAL_TICKS = 100;

	// Translation key of the vanilla "Respawn point set" message - matched by
	// key, not rendered text, so it works regardless of game language.
	private static final String SET_SPAWN_MESSAGE_KEY = "block.minecraft.set_spawn";

	private HttpClient httpClient;
	private WebSocket socket;
	private int tickCounter = 0;
	private boolean wasDead = false;

	// Set by onUseBlock() when the player right-clicks a chest/barrel/shulker
	// box, consumed by onScreenOpen() when the resulting screen appears - the
	// two have to be correlated this way because neither the screen-open
	// packet nor the container menu itself carries a block position at all.
	private BlockPos lastContainerPos;
	private String lastContainerDim;
	private String lastContainerKind;

	// Set by onUseBlock() when the player right-clicks with a block item in
	// hand, consumed one tick later by checkPendingPlacement() - there's no
	// "block was placed" event anywhere in Fabric API, so this is confirmed
	// by checking whether the expected block actually appeared.
	private BlockPos pendingPlacementPos;
	private String pendingPlacementDim;
	private String pendingPlacementItemId;
	private Block pendingPlacementBlock;

	@Override
	public void onInitializeClient() {
		connect();
		ClientTickEvents.END_CLIENT_TICK.register(this::onEndClientTick);
		ClientReceiveMessageEvents.GAME.register(this::onGameMessage);
		UseBlockCallback.EVENT.register(this::onUseBlock);
		ScreenEvents.AFTER_INIT.register(this::onScreenOpen);
		ClientPlayerBlockBreakEvents.AFTER.register(this::onBlockBroken);
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
		LocalPlayer player = client.player;
		if (player == null || socket == null) {
			wasDead = false;
			return;
		}

		// Checked every tick
		checkDeath(player);
		checkPendingPlacement(player);

		// Send player state to the ingest process every STATE_PUSH_INTERVAL_TICKS ticks.
		if (++tickCounter < STATE_PUSH_INTERVAL_TICKS) {
			return;
		}
		tickCounter = 0;

		sendPosition(player);
		sendVitals(client, player);
		sendGameTime(player);
		sendInventory(player);
		sendEquipment(player);
		sendEffects(player);
	}

	private void onGameMessage(Component message, boolean overlay) {
		// "Respawn point set" - sent by the server through the single shared
		// ServerPlayer#setRespawnPosition() path, for a bed click, a
		// successful night's sleep, or a respawn anchor charge alike, only
		// when the position actually changed.
		if (!(message.getContents() instanceof TranslatableContents translatable)
				|| !SET_SPAWN_MESSAGE_KEY.equals(translatable.getKey())) {
			return;
		}
		LocalPlayer player = Minecraft.getInstance().player;
		if (player == null || socket == null) {
			return;
		}
		sendSpawnPoint(player);
	}

	private void sendSpawnPoint(LocalPlayer player) {
		// {"kind":"spawn_point","dim":"minecraft:overworld","pos":[123,64,-79]}
		// Not exposed to the client - using the player's own position
		BlockPos pos = player.blockPosition();
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"spawn_point\",\"dim\":\"%s\",\"pos\":[%d,%d,%d]}",
				dimensionId(player.level()), pos.getX(), pos.getY(), pos.getZ()
		);
		socket.sendText(json, true);
	}

	private InteractionResult onUseBlock(Player player, Level level, InteractionHand hand, BlockHitResult hitResult) {
		// only observes the click
		BlockPos pos = hitResult.getBlockPos();
		Block block = level.getBlockState(pos).getBlock();
		if (block instanceof ChestBlock || block instanceof BarrelBlock || block instanceof ShulkerBoxBlock) {
			lastContainerPos = pos;
			lastContainerDim = dimensionId(level);
			lastContainerKind = BuiltInRegistries.BLOCK.getKey(block).toString();
		}

		// A right-click with a block item in hand is a placement attempt -
		// BlockPlaceContext resolves the exact target position the same way
		// vanilla itself does (including the "replace grass/snow/water
		// instead of the adjacent face" case), so it's reused here rather
		// than reimplemented.
		ItemStack heldStack = player.getItemInHand(hand);
		if (heldStack.getItem() instanceof BlockItem blockItem) {
			BlockPlaceContext placeContext = new BlockPlaceContext(player, hand, heldStack, hitResult);
			pendingPlacementPos = placeContext.getClickedPos();
			pendingPlacementDim = dimensionId(level);
			pendingPlacementItemId = BuiltInRegistries.ITEM.getKey(blockItem).toString();
			pendingPlacementBlock = blockItem.getBlock();
		}

		return InteractionResult.PASS;
	}

	private void checkPendingPlacement(LocalPlayer player) {
		if (pendingPlacementPos == null) {
			return;
		}
		BlockPos pos = pendingPlacementPos;
		String dim = pendingPlacementDim;
		String itemId = pendingPlacementItemId;
		Block expectedBlock = pendingPlacementBlock;
		pendingPlacementPos = null;
		pendingPlacementDim = null;
		pendingPlacementItemId = null;
		pendingPlacementBlock = null;

		if (player.level().getBlockState(pos).getBlock() == expectedBlock) {
			sendPlacement(dim, pos, itemId, "place");
		}
	}

	private void onBlockBroken(ClientLevel level, LocalPlayer player, BlockPos pos, BlockState state) {
		String itemId = BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();
		sendPlacement(dimensionId(level), pos, itemId, "break");
	}

	private void sendPlacement(String dim, BlockPos pos, String itemId, String action) {
		// {"kind":"placement","dim":"...","pos":[x,y,z],"item":"minecraft:torch","action":"place"}
		// Sent for every place/break unfiltered - player_db.write_placement()
		// already applies its own is_notable_placement() allowlist, so
		// duplicating that filter here would just be maintaining it twice.
		// Guarded here (not just by callers) since onBlockBroken() can fire
		// before the ingest connection is up.
		if (socket == null) {
			return;
		}
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"placement\",\"dim\":\"%s\",\"pos\":[%d,%d,%d],\"item\":\"%s\",\"action\":\"%s\"}",
				dim, pos.getX(), pos.getY(), pos.getZ(), itemId, action
		);
		socket.sendText(json, true);
	}

	private void onScreenOpen(Minecraft client, Screen screen, int scaledWidth, int scaledHeight) {
		// Consumed on every screen open, not just container ones - otherwise a
		// stale remembered click could get wrongly attached to some unrelated
		// container screen (e.g. a crafting table) opened much later.
		BlockPos pos = lastContainerPos;
		String dim = lastContainerDim;
		String containerKind = lastContainerKind;
		lastContainerPos = null;
		lastContainerDim = null;
		lastContainerKind = null;

		if (pos == null || !(screen instanceof AbstractContainerScreen<?> containerScreen)) {
			return;
		}

		// Sent when the screen closes, not now - the player can still add or
		// remove items while it's open, and what matters is what they leave
		// behind, not a snapshot from the instant they opened it. (This was
		// the bug behind newly-placed items not showing up: the old code
		// sent the snapshot right here, before the player had touched
		// anything.) The same AbstractContainerMenu object is reused - its
		// slots are mutated in place by sync packets while the screen is
		// open, so reading it again at close time reflects the real result.
		ScreenEvents.remove(screen).register(closedScreen -> sendContainer(containerScreen.getMenu(), dim, pos, containerKind));
	}

	private void sendContainer(AbstractContainerMenu menu, String dim, BlockPos pos, String containerKind) {
		// {"kind":"container","dim":"...","pos":[x,y,z],"container_kind":"minecraft:chest","items":[...]}
		// menu.slots always lists the container's own slots first, followed by
		// the player's 36 hotbar+main slots - true for chests, barrels and
		// shulker boxes alike, confirmed by decompiling their menu classes.
		if (socket == null) {
			return;
		}
		int containerSlotCount = menu.slots.size() - 36;
		StringBuilder items = new StringBuilder();
		for (int i = 0; i < containerSlotCount; i++) {
			ItemStack stack = menu.getSlot(i).getItem();
			if (stack.isEmpty()) {
				continue;
			}
			if (!items.isEmpty()) {
				items.append(',');
			}
			items.append(String.format(Locale.ROOT, "{\"item\":\"%s\",\"count\":%d}", itemId(stack), stack.getCount()));
		}
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"container\",\"dim\":\"%s\",\"pos\":[%d,%d,%d],\"container_kind\":\"%s\",\"items\":[%s]}",
				dim, pos.getX(), pos.getY(), pos.getZ(), containerKind, items
		);
		socket.sendText(json, true);
	}

	private void checkDeath(LocalPlayer player) {
		boolean isDead = player.isDeadOrDying();
		if (isDead && !wasDead) {
			sendDeath(player);
		}
		wasDead = isDead;
	}

	private void sendDeath(LocalPlayer player) {
		// {"kind":"death","dim":"minecraft:the_nether","pos":[40,70,-12],"cause":"minecraft:lava"}
		BlockPos pos = player.blockPosition();
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"death\",\"dim\":\"%s\",\"pos\":[%d,%d,%d],\"cause\":%s}",
				dimensionId(player.level()), pos.getX(), pos.getY(), pos.getZ(), jsonDeathCause(player)
		);
		socket.sendText(json, true);
	}

	private String jsonDeathCause(LocalPlayer player) {
		DamageSource source = player.getLastDamageSource();
		if (source == null) {
			return "null";
		}
		return source.typeHolder().unwrapKey()
				.map(ResourceKey::identifier)
				.map(id -> "\"" + id + "\"")
				.orElse("null");
	}

	private void sendPosition(LocalPlayer player) {
		// {"kind":"position","dim":"minecraft:overworld","pos":[123,64,-79],"biome":"minecraft:plains"}
		BlockPos pos = player.blockPosition();
		// Locale.ROOT, not the platform default - a comma-decimal locale
		// would otherwise produce "123,5" here and break the JSON.
		String json = String.format(
				Locale.ROOT,
				"{\"kind\":\"position\",\"dim\":\"%s\",\"pos\":[%d,%d,%d],\"biome\":\"%s\"}",
				dimensionId(player.level()), pos.getX(), pos.getY(), pos.getZ(), biomeId(player, pos)
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

	private void sendEffects(LocalPlayer player) {
		// {"kind":"effects","effects":[{"id":"minecraft:speed","amplifier":1,"duration":200}, ...]}
		Collection<MobEffectInstance> activeEffects = player.getActiveEffects();
		StringBuilder effects = new StringBuilder();
		for (MobEffectInstance effect : activeEffects) {
			if (!effects.isEmpty()) {
				effects.append(',');
			}
			effects.append(String.format(
					Locale.ROOT,
					"{\"id\":\"%s\",\"amplifier\":%d,\"duration\":%d}",
					effectId(effect), effect.getAmplifier(), effect.getDuration()
			));
		}
		socket.sendText("{\"kind\":\"effects\",\"effects\":[" + effects + "]}", true);
	}

	private String effectId(MobEffectInstance effect) {
		return effect.getEffect().unwrapKey().map(ResourceKey::identifier).map(Object::toString).orElse("unknown");
	}

	private String dimensionId(Level level) {
		// Overworld, Nether or End
		return level.dimension().identifier().toString();
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
