"""Build the frozen independently authored retrieval-v2 evaluation corpus."""

# ruff: noqa: E501 -- authored fixture sentences stay intact for auditability.

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path(__file__).with_name("retrieval_v2.json")

MUSEUM = [
    (
        "a01",
        "fact",
        "The museum's restored 1897 schooner, the Marigold, is permanently dry-docked in Exhibit Hall B for public viewing.",
        None,
        "Where is the historic sailing vessel currently displayed?",
    ),
    (
        "a02",
        "fact",
        "The maritime museum's archive holds 342 original ship logbooks dating from 1850 to 1920, stored in climate-controlled vault C.",
        None,
        "How many old captain's logs are kept in the collection?",
    ),
    (
        "a03",
        "preference",
        "Curator Elena prefers all new artifact acquisitions to be photographed with a grey backdrop before cataloging.",
        None,
        "What's the preferred setup for photographing new items before they're logged?",
    ),
    (
        "a04",
        "preference",
        "The docent team prefers guided tours to start on the hour rather than the half-hour to reduce group overlap.",
        None,
        "Is there a preferred timing convention for starting tours?",
    ),
    (
        "a05",
        "summary",
        "Last quarter's conservation report noted that three brass compasses were restored, two rope samples were stabilized, and the ballast display was repainted; overall the lab completed 85% of its planned workload.",
        None,
        "What has the restoration team accomplished recently according to their status update?",
    ),
    (
        "a06",
        "summary",
        "The annual visitor survey showed attendance rose 12% year over year, with school groups accounting for nearly a third of total visits and the lighthouse exhibit rated the most popular attraction.",
        None,
        "What did this year's guest feedback results reveal about attendance trends?",
    ),
    (
        "a07",
        "event",
        "On June 14th the museum hosted a nighttime lantern tour that drew over 200 attendees and required extra security staffing.",
        None,
        "Was there a special after-hours tour held earlier this summer?",
    ),
    (
        "a08",
        "event",
        "During last week's storm, water intrusion in the east wing damaged two wooden ship models before staff moved them to storage.",
        None,
        "Did the recent bad weather cause any harm to the collection?",
    ),
    (
        "a09",
        "turn",
        "Can you check if the anchor exhibit needs its plaque replaced?",
        "user",
        "What did a staff member ask regarding a display's signage condition?",
    ),
    (
        "a10",
        "turn",
        "I've scheduled the plaque replacement for the anchor exhibit next Tuesday with the fabrication team.",
        "assistant",
        "What update was given about fixing signage on a heavy metal exhibit?",
    ),
    (
        "a11",
        "fact",
        "The museum's diving bell exhibit was acquired from a decommissioned naval vessel in 1962.",
        None,
        "Where did the museum get the piece used for underwater exploration displays?",
    ),
    (
        "a12",
        "fact",
        "The maritime library holds over 4,000 rare nautical charts.",
        None,
        "How many antique navigation maps does the museum's reading room have?",
    ),
    (
        "a13",
        "preference",
        "The curator prefers using brass polish rather than chemical cleaners for compass displays.",
        None,
        "What cleaning method does the curator favor for shining metal navigation instruments?",
    ),
    (
        "a14",
        "preference",
        "The gift shop manager prefers restocking postcards weekly rather than monthly.",
        None,
        "How often does the shop manager like to refresh souvenir card supplies?",
    ),
    (
        "a15",
        "summary",
        "The whale skeleton exhibit hall renovation exceeded its budget by 15% due to new LED lighting installation and structural reinforcements completed in May 2026.",
        None,
        "What happened during the recent upgrade of the large sea creature display room?",
    ),
    (
        "a16",
        "summary",
        "Last quarter's school education program partnered with three local districts, reaching over 900 students through hands-on maritime history workshops.",
        None,
        "How did the outreach collaboration with area schools perform recently?",
    ),
    (
        "a17",
        "event",
        "The museum hosted a naval uniform collection unveiling ceremony on June 5, 2026.",
        None,
        "When did the museum reveal its new display of historic military sailor attire?",
    ),
    (
        "a18",
        "event",
        "A maritime festival featuring rope-making demonstrations took place at the museum on July 4, 2026.",
        None,
        "What outdoor celebration with hands-on cordage crafting happened this summer?",
    ),
    (
        "a19",
        "turn",
        "Do you know what the current pricing tiers are for family museum memberships?",
        "user",
        "What did the visitor ask regarding cost levels for household admission plans?",
    ),
    (
        "a20",
        "turn",
        "The cafe updates its menu seasonally, adding seafood chowder in fall and citrus salads in summer.",
        "assistant",
        "What did the assistant explain about how the eatery's offerings change through the year?",
    ),
]

OBSERVATORY = [
    (
        "b01",
        "fact",
        "The observatory's main telescope is a 2.4-meter reflector housed in the north dome.",
        None,
        "What is the size of the facility's primary telescope?",
    ),
    (
        "b02",
        "fact",
        "The observatory sits at an elevation of 3,200 meters on Mount Verrant.",
        None,
        "How high above sea level is the station situated?",
    ),
    (
        "b03",
        "preference",
        "The lead astronomer prefers scheduling observation sessions during the new moon phase for darker skies.",
        None,
        "When does the head researcher like to plan sky-viewing time?",
    ),
    (
        "b04",
        "preference",
        "Night staff prefer using red-filtered flashlights to preserve their night vision while walking between domes.",
        None,
        "What lighting choice do overnight workers favor when moving outside?",
    ),
    (
        "b05",
        "summary",
        "Over the past winter season, the observatory logged 47 clear nights out of 90, with most cloud cover occurring in February due to storm systems from the western ridge.",
        None,
        "Summarize the observing weather conditions from last winter.",
    ),
    (
        "b06",
        "summary",
        "The annual maintenance review found the secondary mirror coating had degraded by 8%, the dome motor needed lubrication, and backup generators passed all tests.",
        None,
        "What did the yearly equipment checkup reveal?",
    ),
    (
        "b07",
        "event",
        "On March 3rd, a sudden power outage caused the dome shutter to freeze halfway open for six hours during a snowstorm.",
        None,
        "Was there an incident involving an unexpected electrical failure at the site?",
    ),
    (
        "b08",
        "event",
        "A rare aurora display was observed and photographed from the eastern platform on January 12th, drawing visiting researchers from three countries.",
        None,
        "Did any unusual atmospheric light event happen recently at the observatory?",
    ),
    (
        "b09",
        "turn",
        "Can you check if the spectrometer calibration is still valid before tonight's session?",
        "user",
        "What did a user ask regarding confirming instrument readiness before observing?",
    ),
    (
        "b10",
        "turn",
        "The spectrometer was calibrated four days ago and remains within tolerance for tonight's session.",
        "assistant",
        "What was the reply about the current status of an instrument's calibration?",
    ),
    (
        "b11",
        "fact",
        "The observatory's backup generator runs on diesel stored in a 2,000-liter tank behind the maintenance shed.",
        None,
        "How much diesel storage capacity does the backup generator have?",
    ),
    (
        "b12",
        "fact",
        "Staff badge access codes reset automatically every 90 days for security compliance.",
        None,
        "How often do staff access codes get changed?",
    ),
    (
        "b13",
        "preference",
        "Dr. Elena prefers her tea black with no sugar during night shifts.",
        None,
        "What beverage does Dr. Elena like while working nights?",
    ),
    (
        "b14",
        "preference",
        "The night crew prefers classical music playlists over ambient noise in the control room.",
        None,
        "What kind of music does the night crew like in the control room?",
    ),
    (
        "b15",
        "summary",
        "Last month's visitor program hosted 340 guests across twelve guided tours, with feedback highlighting the gift shop's expanded merchandise selection.",
        None,
        "How did last month's public tour program go overall?",
    ),
    (
        "b16",
        "summary",
        "The quarterly budget review concluded that internet bandwidth upgrades are needed to support remote data transfer demands from partner universities.",
        None,
        "What did the recent budget meeting decide about network needs?",
    ),
    (
        "b17",
        "event",
        "On June 3rd, a supply helicopter delivered fresh produce and mail to the station after a two-week gap due to fog.",
        None,
        "When did the helicopter last bring in food and mail?",
    ),
    (
        "b18",
        "event",
        "The observatory hosted a guest lecture by a visiting astrophysicist on exoplanet detection methods last Thursday.",
        None,
        "Who gave the recent talk on finding planets outside our solar system?",
    ),
    (
        "b19",
        "turn",
        "Can you check if the dormitory laundry machines are still out of service?",
        "user",
        "Did someone ask about the status of broken laundry machines?",
    ),
    (
        "b20",
        "turn",
        "I've logged your request to restock the kitchen's coffee supply for next week's delivery.",
        "assistant",
        "What was said about ordering more coffee for the kitchen?",
    ),
]

SHARED = [
    (
        "s01",
        "fact",
        "The Riverside Civic Robotics Club was founded in 2014 by a coalition of local high school teachers and city engineers to promote hands-on STEM education for teenagers.",
        None,
        "When and by whom was our robotics club established?",
    ),
    (
        "s02",
        "fact",
        "The club currently maintains a roster of 47 active members, including 12 mentors who volunteer weekly to guide student teams.",
        None,
        "How many members and mentors does the club have right now?",
    ),
    (
        "s03",
        "preference",
        "The steering committee prefers to schedule all general meetings on the second Tuesday of each month at 6:30 PM to accommodate members' school and work schedules.",
        None,
        "What is the club's preferred timing pattern for regular meetings?",
    ),
    (
        "s04",
        "preference",
        "For all autonomous navigation projects, the technical team prefers using Python with the ROS2 framework over proprietary vendor software.",
        None,
        "Which programming stack does the technical team favor for navigation work?",
    ),
    (
        "s05",
        "summary",
        "Last spring's soldering and circuitry workshop drew 30 attendees, covered basic PCB assembly, and resulted in five student-built sensor kits being donated to the local elementary school.",
        None,
        "Can you recap the outcome of the recent circuitry training session?",
    ),
    (
        "s06",
        "summary",
        "The autumn bake sale and raffle fundraiser raised $3,200 for new competition-grade motors, exceeding the original goal by 60 percent.",
        None,
        "What were the results of the club's fall fundraising drive?",
    ),
    (
        "s07",
        "event",
        "The club's flagship robot, nicknamed Compass, is scheduled to compete in the Regional Civic Bot Challenge on September 14, 2026.",
        None,
        "When is our team's robot entering the upcoming regional competition?",
    ),
    (
        "s08",
        "event",
        "On June 3, 2026, volunteers spent a full Saturday reorganizing the workshop storage room and cataloging spare parts inventory.",
        None,
        "What happened during the recent workshop cleanup day?",
    ),
    (
        "s09",
        "turn",
        "Do we have any spare 12V motors left after the last build season?",
        "user",
        "Someone asked about leftover motor stock from the previous season.",
    ),
    (
        "s10",
        "turn",
        "According to the inventory log, there are eight 12V motors remaining in storage bin C3.",
        "assistant",
        "What was the reported count of remaining motors in storage?",
    ),
    (
        "s11",
        "fact",
        "The club's mobile robot uses ultrasonic sensors mounted at 15 centimeters for obstacle detection.",
        None,
        "How high are the ultrasonic sensors placed on the club's mobile robot?",
    ),
    (
        "s12",
        "fact",
        "The club stores spare 3D-printed gripper fingers in a labeled drawer in the workshop closet.",
        None,
        "Where are extra gripper finger parts kept?",
    ),
    (
        "s13",
        "preference",
        "Members prefer using Fusion 360 over SolidWorks for chassis design because of easier cloud collaboration.",
        None,
        "Which CAD tool does the club favor for chassis modeling?",
    ),
    (
        "s14",
        "preference",
        "The club prefers documenting sensor calibration steps in a shared spreadsheet rather than individual notebooks.",
        None,
        "How does the team like to record calibration procedures?",
    ),
    (
        "s15",
        "summary",
        "Last month the club partnered with the local library to host a robotics demo booth for families, drawing about 40 visitors.",
        None,
        "What happened during the library outreach event recap?",
    ),
    (
        "s16",
        "summary",
        "The club's outreach coordinator reported that a mentorship pairing with a nearby high school robotics team led to a joint sensor-testing session.",
        None,
        "Summarize the mentorship collaboration with the high school team.",
    ),
    (
        "s17",
        "event",
        "On June 14, 2026, the club held an open build session at the community center to test a new robotic arm gripper design.",
        None,
        "When did the club test the new gripper design at the community center?",
    ),
    (
        "s18",
        "event",
        "On July 5, 2026, a sponsor representative visited the workshop to review the club's autonomous navigation demo.",
        None,
        "When did the sponsor visit to see the navigation demo?",
    ),
    (
        "s19",
        "turn",
        "Can we get labeled bins for the spare sensor cables so they don't tangle?",
        "user",
        "What did a member suggest about organizing sensor cables?",
    ),
    (
        "s20",
        "turn",
        "I've added a note to order color-coded labels for the sensor cable bins by next week.",
        "assistant",
        "What follow-up action was promised regarding cable bin labels?",
    ),
]

SCOPE_A = {
    "kind": "private",
    "subject": "eval-v2",
    "environment": "independent-evaluation",
    "owner": "museum-assistant",
}
SCOPE_B = {
    "kind": "private",
    "subject": "eval-v2",
    "environment": "independent-evaluation",
    "owner": "observatory-assistant",
}
SCOPE_SHARED = {
    "kind": "shared",
    "subject": "eval-v2",
    "environment": "independent-evaluation",
    "owner": "robotics-club",
}


def _memories(
    items: list[tuple[str, str, str, str | None, str]], scope: dict[str, str]
) -> list[dict[str, object]]:
    result = []
    for fixture_id, kind, content, role, _ in items:
        memory: dict[str, object] = {
            "fixture_id": fixture_id,
            "kind": kind,
            "content": content,
            "scope": scope,
        }
        if role is not None:
            memory["role"] = role
        result.append(memory)
    return result


def _private_queries(
    items: list[tuple[str, str, str, str | None, str]],
    scope: dict[str, str],
    inaccessible_prefix: str,
) -> list[dict[str, object]]:
    result = []
    prefix = items[0][0][0]
    for index, (fixture_id, _, _, _, query) in enumerate(items):
        distractor = items[(index + 7) % len(items)][0]
        inaccessible = f"{inaccessible_prefix}{index + 1:02d}"
        result.append(
            {
                "query_id": f"q{prefix}{index + 1:02d}",
                "query": query,
                "private_scope": scope,
                "shared_pools": [],
                "expected_fixture_ids": [fixture_id],
                "distractor_fixture_ids": [distractor],
                "inaccessible_fixture_ids": [inaccessible],
            }
        )
    return result


def _shared_queries() -> list[dict[str, object]]:
    result = []
    for index, (fixture_id, _, _, _, query) in enumerate(SHARED):
        private_scope = SCOPE_A if index % 2 == 0 else SCOPE_B
        inaccessible_prefix = "b" if index % 2 == 0 else "a"
        result.append(
            {
                "query_id": f"qs{index + 1:02d}",
                "query": query,
                "private_scope": private_scope,
                "shared_pools": ["robotics-club"],
                "expected_fixture_ids": [fixture_id],
                "distractor_fixture_ids": [SHARED[(index + 7) % len(SHARED)][0]],
                "inaccessible_fixture_ids": [f"{inaccessible_prefix}{index + 1:02d}"],
            }
        )
    return result


def build() -> dict[str, object]:
    return {
        "schema_version": 1,
        "dataset_id": "independent-retrieval-v2",
        "description": "Blind Claude-authored synthetic museum, observatory, and robotics-club memories; contains no user-derived data and was frozen before embedding evaluation.",
        "distractor_policy": "Each query preselects one accessible non-answer seven positions later in the same authored scope; shared queries use a same-domain shared distractor. Each also names one exact-scope-inaccessible control.",
        "top_k": 5,
        "thresholds": {
            "query_count_min": 60,
            "memory_kind_count_min": 12,
            "recall_at_k_min": 0.9,
            "mrr_min": 0.85,
            "distractor_leak_rate_max": 0.1,
            "scope_violation_count_max": 0,
            "runtime_seconds_max": 60,
        },
        "memories": _memories(MUSEUM, SCOPE_A)
        + _memories(OBSERVATORY, SCOPE_B)
        + _memories(SHARED, SCOPE_SHARED),
        "queries": _private_queries(MUSEUM, SCOPE_A, "b")
        + _private_queries(OBSERVATORY, SCOPE_B, "a")
        + _shared_queries(),
    }


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
