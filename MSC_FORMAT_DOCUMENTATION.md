# MSC File Format Documentation

## Overview

`.msc` files are custom script files used for Minecraft server-side scripting, particularly for the Minr server. They provide a high-level language for handling game events, player interactions, and server automation.

---

## 1. File Structure

### Basic Template
```msc
# functionName(Type param1, Type param2)
@using PackageName
@fast
[function body]
```

### Components
- **Header Comment**: Optional function signature with type annotations
- **Directives**: `@using`, `@fast`, etc. at the top of the file
- **Function Body**: The main code logic
- **Inline Comments**: Documentation throughout using `#`

### Example
```msc
# delay(Int ticks)
@using Harha
@fast
@delay {{ticks}}
```

---

## 2. Directives

### Import & Configuration
| Directive | Purpose | Example |
|-----------|---------|---------|
| `@using` | Import/namespace declaration | `@using Harha` |
| `@fast` | Performance optimization flag | `@fast` |
| `@cooldown` | Set execution cooldown | `@cooldown 1` |

### Variable Management
| Directive | Purpose | Example |
|-----------|---------|---------|
| `@define` | First-time declaration of any variable (ALWAYS) | `@define Int count = 5` |
| `@var` | Reassign an existing variable, or call a void function | `@var count = count + 1` |

### Control Flow
| Directive | Purpose | Example |
|-----------|---------|---------|
| `@if` / `@elseif` / `@else` / `@fi` | Conditional blocks | See Control Flow section |
| `@for` / `@done` | Loop blocks | See Control Flow section |
| `@return` | Exit function early | `@return` |

### Execution & Timing
| Directive | Purpose | Example |
|-----------|---------|---------|
| `@delay` | Pause execution | `@delay 2s` or `@delay 30` |
| `@console` | Execute via console | `@console /function execute` |
| `@bypass` | Execute Minecraft command directly | `@bypass /xp set {{player}} 30` |

### Player Interaction
| Directive | Purpose | Example |
|-----------|---------|---------|
| `@player` | Send message to player | `@player &cError message` |
| `@prompt` | Display prompt and await input | `@prompt 30s input "Timeout!"` |
| `@chatscript` | Register chat script | `@chatscript 100s scriptName handler` |

---

## 3. Data Types

### Primitive Types
```msc
Int myNumber = 5
String myText = "hello"
Boolean isActive = true
Float decimalValue = 1.5
Double preciseValue = Double(1.0D)
Long timestamp = system::currentTimeMillis()
Long literalLong = 0L                       # Long literals use the L suffix
Long oneWeekMs = 604800000L                 # Works for any Long value, including in array literals: Long[0L, 1L, 2L]
```

`Long` supports the same arithmetic and comparison operators as `Int` (`+ - * / % == != < <= > >=`). Mixing `Long` and `Int` literals in an expression is fine: `weeksLate + 1L` works.

### Complex Types

#### Player
```msc
Player player = Player("username")
@define String name = player.getName()
@define String gameMode = player.getGameMode()
@define Boolean isOnline = player.isOnline()
@define String challenge = player.getCurrentChallenge()
```

#### Position
```msc
# Position(x, y, z, yaw, pitch, world)
Position spawn = Position(-9199.5, 96.0, 9704.5, 180.0, 10.0, "Theta")
@var x = spawn.getX()
@var y = spawn.getY()
@var world = spawn.getWorld()
```

#### Region
```msc
Region myRegion = Region("regionName", "worldName")
@var players = myRegion.getPlayersInside()
```

### Arrays
```msc
String[] colors = String["#ff0000", "#ff2700", "#ff4e00"]
Int[] numbers = Int[1, 2, 3, 4, 5]
Player[] playerList = Player[]

@var length = colors.length()
@var sum = numbers.sum()
@var hasValue = colors.contains("#ff0000")
```

---

## 4. Variables & Operations

### Variable Declaration

**Critical rule:** The FIRST time a variable name appears, it MUST use `@define`. Every SUBSEQUENT assignment to the same name uses `@var`. This applies regardless of whether the variable will be mutated later — `@define` is the introduction, `@var` is the re-assignment. Using `@var` for a first-time declaration is a syntax error and the script will fail to import.

```msc
@define Int count = 5            # First use → @define (always)
@var count = count + 1           # Subsequent assignments → @var
@var count = 10                  # @var again on every later change

@define String greeting = "hi"   # First use → @define, even if it will be reassigned
@var greeting = greeting + "!"   # Reassignment → @var
```

`@var` is also used (without `=`) to call void functions and to write into per-player or array elements:
```msc
@var doSomething(player)         # Calling a void function
@var board[player][sq] = piece   # Writing an array element (not declaring `board`)
@var board[player].append(0)     # Mutating a stored array
```

The `@prompt` directive does NOT declare its target variable — pre-declare with `@define` first:
```msc
@define String moveStr           # Pre-declare (initial value optional)
@prompt 30s moveStr "Timed out!" # Reads input INTO moveStr
```

### Array/Map Access
```msc
@var blockSelection[player] = "glass"
@var level[player] = 30
@var value = myArray[5]
```

### String Interpolation
```msc
# Basic variable insertion
@player Hello {{playerName}}!

# Function calls
@player Your score: {{getScore(player)}}

# Object methods
@player Name: {{player.getName()}}

# Expressions
@player Next level: {{currentLevel + 1}}
```

### Operators

#### Arithmetic
```msc
@define Int sum = a + b
@define Int diff = a - b
@define Int product = a * b
@define Int quotient = a / b
@define Int remainder = a % b
```

#### Comparison
```msc
@if value == 10
@if count != 0
@if score >= 100
@if age <= 18
@if x > y
@if z < 5
@if name == "Alice"            # == and != work on Strings (literals and array elements)
@if cellSolution[i] == "#"     # Common pattern: sentinel-character checks
```

#### Logical
```msc
@if isActive && hasPermission
@if isDone || isCancelled
@if status == "complete"
```

---

## 5. Control Flow

### Conditionals
```msc
@if condition1
    # Block 1
@elseif condition2
    # Block 2
@else
    # Block 3
@fi
```

**Example:**
```msc
@if score >= 100
    @player &aGreat job!
@elseif score >= 50
    @player &eNot bad!
@else
    @player &cKeep trying!
@fi
```

### Loops
```msc
@for Type variable in collection
    # Loop body
@done
```

**Example:**
```msc
@for Player p in allPlayers
    @player Hello {{p.getName()}}!
@done
```

---

## 6. Functions

### Function Definition
```msc
# functionName(Type param1, Type param2)
@using Harha
@fast

# Function body here
```

### Returning Values

Functions return a value with `@return <expression>`. The function's declared return type lives in the `.nms` signature (see Namespace Files section). A bare `@return` (no expression) exits a void function early.

```msc
# Int factorial(Int n)
@using rychess
@fast

@if n <= 1
    @return 1
@fi
@define Int sub = factorial(n - 1)
@return n * sub
```

```msc
# Boolean checkGridHeightEquals(Int expected)
@using xword
@fast

@return gridHeight == expected
```

A function with a return type can be called as an expression (`@var x = factorial(5)`) or with `@var` to discard the result (`@var factorial(5)` — though most often you call void functions this way). Recursive calls work, including value passthrough across recursion levels.

### Calling Functions
```msc
# Call without return value
@var processPlayer(player)

# Call with return value
@var result = calculateScore(player, bonus)

# Nested calls
@var final = transform(getValue(player))
```

### Common Built-in Functions

#### System Functions
```msc
system::currentTimeMillis()        # Current timestamp in milliseconds
```

#### Math Functions
```msc
math::random(min, max)             # Random number in range
math::floor(value)                 # Floor function
math::abs(value)                   # Absolute value
```

#### List Functions
```msc
list::range(start, end)            # Create range [start, end)
```

---

## 7. Player Messaging

### Text Formatting
```msc
@player &cRed text
@player &aGreen text
@player &eYellow text
@player &l&nBold and underlined
@player &#ffaa00Custom hex color
```

### Color Codes
| Code | Color | Code | Format |
|------|-------|------|--------|
| `&0` | Black | `&l` | Bold |
| `&1` | Dark Blue | `&m` | Strikethrough |
| `&2` | Dark Green | `&n` | Underline |
| `&3` | Dark Aqua | `&o` | Italic |
| `&4` | Dark Red | `&r` | Reset |
| `&5` | Dark Purple | | |
| `&6` | Gold | | |
| `&7` | Gray | | |
| `&8` | Dark Gray | | |
| `&9` | Blue | | |
| `&a` | Green | | |
| `&b` | Aqua | | |
| `&c` | Red | | |
| `&d` | Light Purple | | |
| `&e` | Yellow | | |
| `&f` | White | | |

### Hex Colors
```msc
@player &#ff0000Pure red
@player &#00ff00Pure green
@player &#0000ffPure blue
```

---

## 8. Minecraft Commands

### Command Execution
```msc
# Execute raw Minecraft command
@bypass /command arguments
```

### Common Command Patterns

#### Experience & Levels
```msc
@bypass /xp set {{player}} 30 levels
@bypass /xp add {{player}} 100 points
```

#### Titles & Subtitles
```msc
@bypass /title {{player}} title ["",{"text":"Title","bold":true,"color":"gold"}]
@bypass /title {{player}} subtitle ["",{"text":"Subtitle","color":"gray"}]
@bypass /title {{player}} times 10 70 20
```

#### Sound Effects
```msc
@bypass /playsound minecraft:block.note_block.pling master {{player}} ~ ~ ~ 1 0.707
@bypass /playsound minecraft:entity.player.levelup master {{player}} ~ ~ ~ 1 1.5
```

#### Particles
```msc
@bypass /particle minecraft:explosion_emitter ~ ~ ~ 2 1 2 0.5 500 force @a
@bypass execute at {{player}} anchored feet run particle minecraft:flame ~ ~1 ~ 0.2 0.5 0.2 0.01 20
```

#### Player Attributes
```msc
@bypass /attribute {{player}} minecraft:scale base set 1
@bypass /gamemode {{gameMode}} {{player}}
@bypass clear {{player}}
```

#### Teleportation
```msc
# Using Position object
player.teleport(Position(-9199.5, 96.0, 9704.5, 180.0, 10.0, "Theta"))

# Using command
@bypass /tp {{player}} -9199 96 9704
```

#### Items & Inventory
```msc
@bypass /item replace entity {{player}} container.0 with {{item}}[custom_name={"italic":false,"text":"‌"}]
@bypass /clear {{player}} minecraft:stone
```

---

## 9. Timing & Delays

### Delay Syntax
```msc
@delay 1        # 1 tick delay (~0.05 seconds)
@delay 20       # 20 ticks (1 second)
@delay 30       # 30 ticks (1.5 seconds)
@delay 2s       # 2 seconds
@delay 100s     # 100 seconds
```

### Common Timing Patterns
```msc
# Short delay for animation
@delay 5
@player &aStep 1
@delay 5
@player &aStep 2

# Longer delay for cooldown
@delay 3s
@player &eCooldown complete!
```

---

## 10. Comments & Documentation

### Single-Line Comments
```msc
# This is a comment
@var x = 5  # Cannot have inline comments
```

### Function Documentation
```msc
# functionName(Type param1, Type param2)
# Description of what the function does
# Optional: URL to paste or external reference
```

### Section Comments
```msc
# ==========================================
# SECTION NAME
# ==========================================

# Subsection explanation
@define String value = "test"
```

---

## 11. Common Patterns & Best Practices

### Function File Organization
```
Harha/
├── __init__.msc              # Main initialization
├── delay.msc                 # Utility functions
├── formatNumber.msc          # Helper functions
├── handleFalling.msc         # Event handlers
├── respawnFunction.msc       # Game logic
└── cosmeticGlass.msc         # Cosmetic features
```

### Naming Conventions
- **Functions**: camelCase (e.g., `calculateScore`, `handleFalling`)
- **Variables**: camelCase (e.g., `playerName`, `currentLevel`)
- **Constants**: camelCase (e.g., `maxPlayers`, `spawnPoint`)
- **Files**: camelCase with `.msc` extension

### Performance Optimization
```msc
# Mark frequently-called functions as fast
@fast

# Use @define for constants
@define Int MAX_LEVEL = 100

# Minimize delays in loops
@for Player p in players
    # Fast operations only
@done
```

### Error Handling Pattern
```msc
@if !player.isOnline()
    @return
@fi

# Continue with logic knowing player is online
```

### Array Bounds Checking
```msc
@if index >= 0 && index < array.length()
    @var value = array[index]
@else
    @player &cInvalid index!
@fi
```

---

## 12. Advanced Features

### Chat Scripts
```msc
# Register a chat script with timeout
@chatscript 100s scriptName handlerFunction

# When player types in chat within 100 seconds,
# handlerFunction will be called with the message
```

### Prompt System
```msc
# Prompt with timeout and variable storage
@prompt 30s userInput "You took too long!"

# userInput now contains player's response
@player You said: {{userInput}}
```

### Region Detection
```msc
@define Region spawn = Region("spawn", "Theta")
@var playersInside = spawn.getPlayersInside()

@for Player p in playersInside
    @player Welcome to spawn!
@done
```

### Style Point System Example
```msc
# Calculate color based on prestiges
@define Int colorIndex = (stylePointPrestiges[player] * 8) % colorList.length()
@define String color = colorList[colorIndex]

# Display with formatting
@bypass /title {{player}} title ["",{"text":"{{title}}","bold":true,"color":"{{color}}"}]
```

### Time-based Calculations
```msc
@define Long startTime = system::currentTimeMillis()
# ... do work ...
@define Long endTime = system::currentTimeMillis()
@define Long duration = endTime - startTime
@player Took {{duration}}ms
```

---

## 13. Complete Example: Complex Function

```msc
# respawnFunction(Player player, String reason)
# https://paste.minr.org/example
@using Harha
@fast

# Validate player is online
@if !player.isOnline()
    @return
@fi

# Get respawn location based on current stage
@define Int stage = currentStage[player]
@define Position respawnPos = Position(0.0, 100.0, 0.0, 0.0, 0.0, "Theta")

@if stage == 1
    @var respawnPos = Position(-9199.5, 96.0, 9704.5, 180.0, 10.0, "Theta")
@elseif stage == 2
    @var respawnPos = Position(-9199.5, 96.0, 9750.5, 180.0, 10.0, "Theta")
@else
    @player &cInvalid stage!
    @return
@fi

# Teleport with effects
@bypass /playsound minecraft:entity.enderman.teleport master {{player}} ~ ~ ~ 1 1
player.teleport(respawnPos)
@delay 5

# Send message based on reason
@if reason == "fall"
    @player &eYou fell! Respawning...
@elseif reason == "void"
    @player &cYou fell into the void!
@else
    @player &aRespawning...
@fi

# Reset player state
@bypass /xp set {{player}} 0 levels
@bypass clear {{player}}
@bypass /effect clear {{player}}
@bypass /attribute {{player}} minecraft:scale base set 1

# Track respawn count
@var respawnCount[player] = respawnCount[player] + 1

# Display respawn count
@delay 1s
@player &7Respawns: &f{{respawnCount[player]}}
```

---

## 14. File Types & Categories

### Utility Functions
Small, reusable helper functions
- `delay.msc` - Simple delay wrapper
- `formatNumber.msc` - Number formatting
- `duckFunction.msc` - Data processing

### Event Handlers
Respond to game events
- `handleFalling.msc` - Fall detection
- `handlePlacement.msc` - Block placement
- `handleStylePoints.msc` - Style point calculation

### Game Logic
Core gameplay mechanics
- `respawnFunction.msc` - Player respawning
- `secretFound.msc` - Secret discovery
- `finalAnimation.msc` - End-game sequences

### Cosmetic Systems
Visual effects and customization
- `cosmeticGlass.msc` - Glass cosmetics
- `bird.msc` - Bird particle effects
- `swagTitle.msc` - Title displays

### Initialization
Startup and configuration
- `__init__.msc` - Main initialization
- `startSignPrep.msc` - Sign preparation
- `pcStats.msc` - Player statistics

---

## 15. Quick Reference

### Frequently Used Snippets

```msc
# Get current time
@define Long now = system::currentTimeMillis()

# Random number
@define Int random = math::random(1, 100)

# Check if player is online
@if player.isOnline()

# Array length
@define Int size = myArray.length()

# Format a number with commas
@var formatted = formatNumber(123456)

# Play success sound
@bypass /playsound minecraft:entity.player.levelup master {{player}} ~ ~ ~ 1 1.5

# Show title
@bypass /title {{player}} title ["",{"text":"Success!","bold":true,"color":"green"}]

# Teleport player
player.teleport(Position(x, y, z, yaw, pitch, "world"))

# Send colored message
@player &#00ff00Green text with hex color

# Wait 1 second
@delay 1s

# Loop through players
@for Player p in playerList
    @player Hello {{p.getName()}}!
@done
```

---

## 16. Namespace Files (`.nms`)

A namespace file (`.nms`) declares the **state and function signatures** that a related set of `.msc` script files share. Each `.msc` file in the namespace's directory implements one function whose signature is declared in the `.nms`. Think header file: `.nms` declares, `.msc` defines.

### Basic structure

```msc
@namespace myproject

# Namespace globals (shared across all callers)
    Int counter = 0
    String[] log = String[]

# Per-player slots (each player gets their own copy)
    relative Int score = 0
    relative String[] inventory = String[]

# Function signatures
    Int addToCounter(Int delta)
    appendLog(String message)
    rewardPlayer(Player player, Int amount)

@endnamespace
```

Each `.msc` file under `myproject/` implements one function and starts with `@using myproject` + `@fast`. The first comment block in the `.msc` file is the function's documentation. The filename must match the function name.

### State scoping: `relative` vs plain

| Declaration | Scope | Access |
| --- | --- | --- |
| `Int counter = 0` | Namespace global. Single shared value across all callers. | `counter`, `@var counter = ...` |
| `relative Int score = 0` | Per-player slot. Each player has their own value. | `score[player]`, `@var score[player] = ...` |

**Plain (non-`relative`) namespace globals are mutable from `.msc` files**, and writes persist across function-call boundaries. A `@var counter = 5` in one `.msc` file is visible to a read in any other `.msc` file in the same namespace. This is the foundation for shared/room-scoped state — a single chess game per room, an active puzzle, a global leaderboard, etc. Plain and `relative` declarations coexist freely; writes to one do not smear into the other.

```msc
# fileA.msc - sets a global
@using myproject
@fast
@var counter = 5

# fileB.msc - reads it back; sees 5
@using myproject
@fast
@return counter
```

### No class system

MSC has no `@class` / `struct` construct. Model "objects" with **parallel arrays at namespace scope**, all keyed by the same index:

```msc
# Instead of: class Cell { String letter; Int acrossIdx; Int downIdx; }
    String[] cellLetter = String[]
    Int[] cellAcrossIdx = Int[]
    Int[] cellDownIdx = Int[]
```

A 2D grid flattens to 1D: `idx = row * width + col`. Lists of objects become one array per field. The same trick works for `relative` per-player records.

### No dynamic constant lookup

You cannot resolve a constant by computed name (no `getNamespaceConst("piece" + i)`). When you need "look up the data block for id N", write a hand-coded `@if` / `@elseif` chain that assigns or returns the right values per branch. The pattern scales fine to dozens of branches and is friendly to code-generation:

```msc
# loadPuzzleData(Int id)
@using xword
@fast

@if id == 0
    @var gridHeight = 3
    @var gridWidth = 3
    @var cellSolution = String["#", "A", "T", "T", "E", "A", "E", "S", "T"]
    @return
@elseif id == 1
    @var gridHeight = 5
    @var gridWidth = 5
    @var cellSolution = String[...]
    @return
@fi

@player &cloadPuzzleData: unknown id {{id}}
```

### Array initialization, mutation, and append

`String[]` and `Int[]` namespace globals support the full set of operations from `.msc` files:

```msc
@var cellSolution = String["A", "B", "#", "D", "E"]   # Replace whole array
@var cellSolution[1] = "X"                            # Element assignment
@var cellSolution.append("F")                         # Append (length grows)
@define Int n = cellSolution.length()                 # Read length
@if cellSolution[2] == "#"                            # Index read + equality
    # ...
@fi
```

The `relative` form takes the player index first: `@var savedGuesses[player] = String["X", "Y"]`, `@var savedGuesses[player].append("Z")`, `savedGuesses[player].length()`, `savedGuesses[player][1]`.

### Verifying assumptions

Some `.nms` patterns aren't visible elsewhere in the codebase (e.g. writing to a non-`relative` global). Before scaling out a feature that depends on an unproven assumption, write a focused MSC test function that prints `PASS` / `FAIL` to the player and run it in-game. The cost is one small `.msc` file; the value is catching a model-breaking pitfall before 30 dependent files exist.

---

## Conclusion

The `.msc` format provides a powerful scripting language specifically designed for Minecraft server automation. It combines:
- **Simple syntax** for quick script writing
- **Strong typing** for better error prevention
- **Built-in Minecraft integration** with `@bypass` and player objects
- **Flexible control flow** with conditionals and loops
- **Performance optimization** through `@fast` directive
- **Player interaction** through messages, prompts, and chat scripts

This documentation covers the core features observed across the Harha codebase. For specific implementation details, refer to individual `.msc` files in the project.
