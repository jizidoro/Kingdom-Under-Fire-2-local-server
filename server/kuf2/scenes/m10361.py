"""Lunawing Sortie I 10361 (1_MistField zone6), the director's table.
The original's script, from the playlist, with its storyboard and our marks: planning/scripts/missions/10361.md
(`py tools/mission_scripts.py 10361`).

Sources: the map's missiontext (lines 8100-8290; `py tools/recon/mission_sheet.py 10361`; the panel 8500-8540 "Move
to New Hampton" / "Let the Lunawing be destroyed" is game.mission_text's), the zone's bounds and forces, the
walkthrough (walkthrough_guide.txt L167-177: "Escape Azilia", invincible, the temporary troop Lunawing and its four
skills; planning/walkthrough/p3-luna-hampton.md steps 4-5). Mist Field's missiontext serves six spots: the other
blocks (901, 3000-3500, 5000-5970, 6000-6130, 7000-7830) are the field's and Grey Fog Street's.

Speakers, from the lines' own words and the crew's other lines on this map: Glen commands ("Our destination is New
Hampton", "let's go to Hironeiden"); Golden Hammer is the engineer who refloated the Lunawing (3100-3104: the backup
engine, the fuel, the Crystal Stones) and laughs "Hah hah hah"; Jade is Moonlight's student who knew the airship
(3000-3006, 5530), so the Encablossians "reacting to the Lunawing" are hers. The crew (force 10100: Glen, Thompson,
Golden Hammer, Jade, Jager) stands in the room from the start, so every line shows a name and a face.

Ours: the speaker of the lines no character's words fix (8110, 8130, 8180, 8240, 8270, 8280: Thompson; 8290: Glen),
and which trigger starts each scene, read from the bound names: 시작 "start" (the remnants 강조1-3, "emphasis", stand
7-9k from it), 엔카가이상하군요 "the Encablossians are strange" (8180's own words), 우쭈쭈대사 "the cooing line" (8280's
patronising praise), 골든해머_대사 "Golden Hammer's line", 포스활성화_22000 "force 22000 activates", 글렌_돌아가자 "Glen:
let's go back" (8260, back to Hironeiden), 제이드_대사 "Jade's line" (8220, the last named bound before the flight over
the range to 목적지). The head cannons' warning comes as the airship comes within reach of the remnants' head cannons
10308 / 10309 (below), the rally as force 23000 (the colossus and the scorpions) wakes. No "won" step: the map has no
Sortie I ending; the story goes on in Sortie II's
own text (10362, 1_NewHamptonHighway 6100 "We've left Azilia and entered Eastern Hironeiden"). The win goes on into
Sortie II (NEXT = 622: warpinfo 622, MISSION, 10362 group 1, the only warp to 10362 and used by nothing else in the
data; the tape, part 3: Glen's 8260 at 4:56, no window and no field, the loading screen "New Hampton Highway" at 5:23,
Sortie II's panel 5:58; storyboard captures/scripts/10362/board_1.jpg tiles #5-#7); Sortie II's own win ends at the
quest's end spot, the crash site 10351.

Left out: 8170 "Oops, I don't think she's completely repaired" answers the player using the Lunawing's 4th-slot skill
(8160), a moment the director cannot see; 8020 "We shouldn't go there" (leaving the area); the guide notices 8030 / 8040
(@MRB), 8050 (8000 / 8010 is shown after 8140, as in the original); the HUD labels 8550 / 8560; the draft 8200 / 8210
("The longer we stay here ...", "Let's get out of here"): the tape (part 3, frames 3:18-3:52) goes from Jade's 8190 to
Glen's 8250 and Golden Hammer's 8270 with no line between (an empty help box 3:33-3:42).

"Lunawing Shield" (8570) is the troops bar under the quest tracker (ActGuiAddTroopsBarToMissionSituation 0xc8b4, read
2026-10-24: game.ACT_SITUATION_TROOPS_BAR): the airship's portrait, the label and a cyan bar, full from 2:30 to 4:50 on
the tape (the ship is untouchable). Ours from the code and the frames; not yet seen in our client.

Thompson's 8240 "Ah, watch out! There are Head Cannons around here!": the tape shows it 10 s before Jager's 8180 at
엔카가이상하군요 (his box at 3:07.50, frames build/order-b captures/order-b/p3_luna_8240_zoom.jpg), as a head cannon
walks into view ahead of the ship (3:06.0), before the player targets it (3:08.0) and it fires (3:09.5). Where the ship
was then (about 16 k past 시작 on the straight route at the tape's ~900 units/s), the remnants F20000's own head cannons
10308 / 10309 stand 1.8-1.9 k off the route, abreast. Ours: a "near" step, the ship within their acquisition range
(165030 RANGE_ACQUISITION 6000: they can target it), which comes ~6 s before the tape's moment on that route, still
after 시작's lines and before 엔카가이상하군요 (it was F21000's proximity wake, after that bound: 18 k on, 26 s after it in
the live runs of 2026-10-09). No bound lies there, an engage is the melee state, the ship's hp never moves."""
GLEN, THOMPSON, GOLDEN_HAMMER, JADE = "글렌", "톰슨", "골든해머", "제이드"

HOLD = {22000}                   # its own bound brings it (the proximity wake had it 34k early, the authoring run)
NEXT = 622                       # the win goes on into Sortie II 10362 (see above)

# Speakers checked against the original (playthrough part 3, 2:28-4:56, planning/scripts/
# 10358-10233-10234-10235-10362_6uClEdAS__k_000.md): 8130 and 8270 are Golden Hammer's, 8180 Jager's.
STEPS = [
    # take-off: New Hampton is the destination, the airship flies and can attack (8100-8120)
    # (the original's "Lunawing Shield", 8570, is not a panel line: a widget under the quest tracker with the airship's
    # icon and a blue bar, frames of part 3 2:34-4:50; the troops bar ActGuiAddTroopsBarToMissionSituation 0xc8b4,
    # whose typed arguments are to probe live before we send it)
    # Mist Field camera30003 is its only interactive map camera (nInputSignal38), with eye/target axis5.
    # Bind axis5 to the airship before selecting it; ordinary tactical camera10054 clips into the hull.
    # Selection is reconstructed from shipped data + native probe; original server Lua is unavailable.
    # Original part3 frames120/140 retain HP77610 under fire; the guide explicitly
    # says invincible. Reconstructed mission protection, not a generic allied HP floor.
    # The separate shield gauge/its script resource are still unresolved.
    {"on": "start", "do": [("untouchable troop", 10000, 1), ("troops bar", 8570, 10000), ("camera troop", 10000, 30003),
                            ("say", GLEN, 8100), ("say", THOMPSON, 8110), ("say", GOLDEN_HAMMER, 8120)]},
    # the remnants ahead (force 20000's 강조1-3): test the Lunawing's attack on them
    {"on": "bound", "bound": "시작", "do": [("say", GOLDEN_HAMMER, 8130), ("say", GOLDEN_HAMMER, 8140), ("notice", 8000, 8010)]},
    # the Encablossians follow the airship: clear them and go (the tape 3:18-3:52: 8180 Jager's, 8190 Jade's, 8250
    # Glen's, 8270 Golden Hammer's, one run; ours had 8200 / 8210 here and 8250 / 8270 with the head cannons and F22000)
    {"on": "bound", "bound": "엔카가이상하군요", "do": [
        ("say", None, 8180), ("say", JADE, 8190), ("say", GLEN, 8250),       # 8180 is Jager's, not in the room
        ("say", GOLDEN_HAMMER, 8270)]},
    # the remnants' head cannons (F20000's 10308 / 10309, abreast of the route 16-17 k past 시작) can target the ship
    {"on": "near", "troop": (10308, 10309), "do": [("say", THOMPSON, 8240)]},
    # the colossus and the scorpions (force 23000), then the teasing praise
    {"on": "wake", "force": 23000, "do": [("say", GLEN, 8290)]},
    {"on": "bound", "bound": "우쭈쭈대사", "do": [("say", THOMPSON, 8280)]},
    # Golden Hammer: she can do more, the skill in the 4th slot
    {"on": "bound", "bound": "골든해머_대사", "do": [("say", GOLDEN_HAMMER, 8150), ("say", GOLDEN_HAMMER, 8160)]},
    # force 22000 comes in at its bound, then Glen calls it enough (8260, the tape 4:56)
    {"on": "bound", "bound": "포스활성화_22000", "do": [("wake", 22000)]},
    {"on": "bound", "bound": "글렌_돌아가자", "do": [("say", GLEN, 8260)]},
    # past the battle: over the mountain range they cannot follow
    {"on": "bound", "bound": "제이드_대사", "do": [("say", JADE, 8220), ("say", GOLDEN_HAMMER, 8230)]},
]
