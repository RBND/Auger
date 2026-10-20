# How to Set Your Server's Gameplay Rules (Sandbox Code)

Your server's gameplay rules (difficulty, loot amount, XP speed, day length, blood moon frequency, zombie speed and much more) are all stored in **one short code** called a **Sandbox Code**.

You don't type this code yourself. The game creates it for you, and you copy and paste it into Auger. This guide walks you through it.

> **Time needed:** about 3 minutes
> **You need:** 7 Days to Die installed on your PC through Steam (the normal game, not just the server)

---

## Part 1: Create and copy the code in the game

1. **Start 7 Days to Die** from your Steam library, just like you would to play.
   - For best results, use the same game version as your server (for example, don't mix a stable game with an experimental server).
2. On the main menu, click **Play Game**, then **New Game**.
3. Open **Sandbox Options**.
4. **Choose your rules.** Either pick one of the game's presets, or change individual settings such as:
   - Difficulty, zombie speed and zombie numbers
   - Day length and blood moon frequency
   - Loot amount, XP multiplier and crafting speed
5. Click the **Copy** button on the Sandbox Options screen. The code is now on your clipboard. It looks something like `AAAJABJACJADJARFBNC`.
6. You can now **close the game**. You don't need to actually start a world.

> **Tip:** If you're not sure what to change, just pick a preset. You can always come back and make a new code later.

---

## Part 2: Paste the code into Auger

1. Open **Auger**.
2. Click the **⚙️ Config Editor** tab.
3. Near the top, find the section called **🧩 Gameplay Rules (Sandbox Code)**.
4. Click **📋 Paste from Clipboard**.
   - Or click in the *Sandbox Code* box and press **Ctrl+V**.
   - Auger automatically removes extra spaces or quotes. You can even paste a whole `<property name="SandboxCode" value="..."/>` line and Auger will pull out the code.
5. Click **💾 Save Config** at the bottom of the tab.
6. **Restart your server** if it was already running. New rules only apply when the server starts.

Can't remember these steps? Click the **❓ How do I get a code?** button next to the Sandbox Code box. It shows this same guide inside Auger.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| "Clipboard Empty" when I click Paste | Go back to the game's Sandbox Options and click **Copy** again, then paste straight away (copying anything else replaces it). |
| "Not a Sandbox Code" / "Invalid Sandbox Code" | You copied something else. Copy the code from the game again. |
| My friends don't see the new rules | Make sure you clicked **💾 Save Config**, then **restart the server**. |
| I want to go back to the default rules | Click **🔄 Reset to Defaults** in the Config Editor (Auger saves a backup of your old settings first), or paste a new code made from a game preset. |
| I don't own the game on this PC | Create the code on any PC that has the game, send the text to yourself (email, Discord, etc.), and paste it into Auger. |

---

## Good to know

- **Updating the server won't erase your code.** Auger backs up `serverconfig.xml` before every server update and restores it afterwards.
- **Every save makes a backup.** Auger keeps timestamped copies (`serverconfig_YYYYMMDD_HHMMSS.xml.bak`) in your server folder.
- Each code holds the whole set of rules. Pasting a new one replaces all the previous gameplay rules at once.
