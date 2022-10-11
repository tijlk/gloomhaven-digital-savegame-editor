import re
from datetime import datetime
import struct


class SaveGameEditor:
    def __init__(self, ext=".dat", root_dir=None, campaign=None):
        self.root_dir = root_dir
        self.campaign = campaign
        self.file = f"{self.root_dir}/{self.campaign}/{self.campaign}{ext}"
        self.read_savegame()
        self.save_backup_savegame()
        self.scenario_state_dict = {
            0: "None",
            1: "Locked",
            2: "Unlocked",
            3: "InProgress",
            4: "Completed",
            5: "Blocked",
            6: "InProgressCasual"
        }

    def save_backup_savegame(self):
        now_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        with open(f"{self.file}-backup-{now_str}", 'wb') as f:
            f.write(self.txt)

    def read_savegame(self):
        with open(self.file, 'rb') as f:
            self.txt = f.read()

    def save_savegame(self):
        with open(self.file, 'wb') as f:
            f.write(self.txt)

    def read_events(self):
        res = re.search(b"(?s)_City_Campaign_[a-zA-Z0-9]*ID(?!.{6}E)", self.txt)
        city_pattern = b"Event_City_Campaign_([a-zA-Z0-9]*)ID"
        self.city_events = [n for n in re.findall(city_pattern, self.txt[:res.span()[1]])]
        self.n_city_events = len(self.city_events)
        res = re.search(b"(?s)_Road_Campaign_[a-zA-Z0-9]*ID(?!.{6}E)", self.txt)
        road_pattern = b"Event_Road_Campaign_([a-zA-Z0-9]*)ID"
        self.road_events = [n for n in re.findall(road_pattern, self.txt[:res.span()[1]])]
        self.n_road_events = len(self.road_events)

    @staticmethod
    def replace_substring_inplace(txt, substr, span):
        return txt[:span[0]] + substr + txt[span[1]:]

    @staticmethod
    def prettify_events(events):
        return " ".join([e.decode("utf-8") for e in events])

    def print_events_info(self, event=None):
        self.read_events()
        if event == "city" or event is None:
            print(f"{self.n_city_events} City Events:")
            print(f"Current order: {self.prettify_events(self.city_events)}")
            print(f"Sorted: {self.prettify_events(sorted(self.city_events))}")
        if event is None:
            print("")
        if event == "road" or event is None:
            print(f"{self.n_road_events} Road Events:")
            print(f"Current order: {self.prettify_events(self.road_events)}")
            print(f"Sorted: {self.prettify_events(sorted(self.road_events))}")

    @staticmethod
    def get_events_span(events_txt, event="city"):
        event_capital = b"City" if event == "city" else b"Road"
        return [
            {"event_number": int(re.search(b'_([0-9]*)ID', e.group()).group(1)),
             "event_span": e.span()}
            for e in list(re.finditer(
                b"(\x17|\x18)Event_" + event_capital + b"_Campaign_[a-zA-Z0-9]*ID",
                events_txt
            ))
        ]

    @staticmethod
    def next_power_of_2(x, min_power=2):
        return max(2 ** min_power, 1 if x == 0 else 2 ** (x - 1).bit_length())

    def replace_events(self, event="city", new_events=None, verbose=True):
        event_capital = b"City" if event == "city" else b"Road"
        if not new_events:
            print("You didn't specify new events to replace the existing events with!")
            return

        # Find the location of the event data within the full text
        events_start_index = list(
            re.finditer(b"Event_" + event_capital + b"_Campaign_[a-zA-Z0-9]*ID", self.txt)
        )[0].start() - 10
        events_end_index = list(
            re.finditer(b"(?s)_Campaign_[a-zA-Z0-9]*ID(?!(\n|\r.)*.{6}E)((?:\n|\r.)*)", self.txt[events_start_index:])
        )[0].end() + events_start_index

        # Get first BinaryObjectString object ID
        first_event_object_id = struct.unpack("<I", self.txt[events_start_index + 5:events_start_index + 9])[0]

        # Number of events submitted
        n_events = len(new_events)

        # Create the new events txt
        # define the length of the array in which to store the events, which should be a power of 2
        array_length = self.next_power_of_2(n_events)  # define the length of the a
        new_events_txt = struct.pack('<I', array_length)  # the length of the array in little endian

        # Create string excluding ID
        event_string_noid = b"Event_" + event_capital + b"_Campaign_"

        # now add the stuff for each event
        for i, new_event in enumerate(new_events):
            new_events_txt += b"\x06"  # record type 6
            new_events_txt += struct.pack("<I",
                                          first_event_object_id + i)  # first BinaryObjectString object ID--applied to every BinaryObjectString in array
            new_events_txt += len(event_string_noid.decode('utf-8') + str(new_event) + "ID").to_bytes(1,
                                                                                                      "little")  # the length of the string defining the event
            new_events_txt += event_string_noid + bytes(str(new_event), "utf-8") + b"ID"
        if array_length - n_events > 1:
            n_nulls = array_length - n_events
            # If there is more than one space left in the array, add a ObjectNullMultiple256 (13 = \r)
            # and the number of nulls to add
            new_events_txt += b"\r" + n_nulls.to_bytes(1, "little")
        elif array_length - n_events == 1:
            # If there is exactly one space left in the array, add a single null (10 = \n)
            new_events_txt += b"\n"
        else:
            # If there are no spaces left in the array, we're finished
            pass

            # Check for discard deck.
        next_deck = b"Event_Road_Campaign_" if event == "city" else b"PERSONALQUEST_"  # Next array in save file. Used to find end of discard deck if present.

        # Find the possible location of the event discard deck within the full text
        discard_start_index = events_end_index
        discard_end_index = list(
            re.finditer(next_deck, self.txt[discard_start_index:])
        )[0].start() - 15 + discard_start_index

        # Test for presence of discard deck (is discard deck between event deck and next deck)
        if discard_start_index != discard_end_index:
            # add empty discard deck
            discard_array_length = struct.unpack("<I", self.txt[discard_start_index + 5:discard_start_index + 9])[0]

            new_events_txt += self.txt[discard_start_index:discard_start_index + 9]  # array, object ID, array size
            if discard_array_length > 1:
                # If there is more than one space in the array, add a ObjectNullMultiple256 (13 = \r)
                # and the number of nulls to add
                new_events_txt += b"\r" + discard_array_length.to_bytes(1, "little")
            elif discard_array_length == 1:
                # If there is exactly one space in the array, add a single null (10 = \n)
                new_events_txt += b"\n"
            else:
                # If there are no spaces left in the array, add no nulls. This case should not happen as it would softlock the game.
                pass
        else:
            # If there is no discard deck, we're finished
            pass

        self.txt = self.replace_substring_inplace(self.txt, new_events_txt, (events_start_index, discard_end_index))
        self.print_events_info(event=event)

    def update_char_values(self, char_name="Sol Goodman", gold=None, exp=None, perk_points=None, perk_checks=None):
        char_info_span = re.search(bytes(char_name, "utf-8") + b'(?s:.)*?ID(.*)\n\n', self.txt).span(1)
        gold_span = (char_info_span[0], char_info_span[0] + 4)
        exp_span = (char_info_span[0] + 4, char_info_span[0] + 8)
        level_span = (char_info_span[0] + 8, char_info_span[0] + 12)
        perk_points_span = (char_info_span[1] - 12, char_info_span[1] - 8)
        perk_checks_span = (char_info_span[1] - 8, char_info_span[1] - 4)
        current_gold = struct.unpack("<I", self.txt[gold_span[0]:gold_span[1]])[0]
        current_exp = struct.unpack("<I", self.txt[exp_span[0]:exp_span[1]])[0]
        current_level = struct.unpack("<I", self.txt[level_span[0]:level_span[1]])[0]
        current_perk_points = struct.unpack("<I", self.txt[perk_points_span[0]:perk_points_span[1]])[0]
        current_perk_checks = struct.unpack("<I", self.txt[perk_checks_span[0]:perk_checks_span[1]])[0]
        if gold is not None:
            new_gold_str = struct.pack('<I', gold)
            self.txt = self.replace_substring_inplace(self.txt, new_gold_str, gold_span)
            new_gold = struct.unpack("<I", self.txt[gold_span[0]:gold_span[1]])[0]
            print(f"{char_name}'s gold amount was updated from {current_gold} to {new_gold}.")
        else:
            print(f"{char_name} currently has {current_gold} gold.")
        if exp is not None:
            new_exp_str = struct.pack('<I', exp)
            self.txt = self.replace_substring_inplace(self.txt, new_exp_str, exp_span)
            new_exp = struct.unpack("<I", self.txt[exp_span[0]:exp_span[1]])[0]
            print(f"{char_name}'s experience was updated from {current_exp} (level {current_level}) to {new_exp}.")
        else:
            print(f"{char_name} currently is level {current_level} with {current_exp} experience.")
        if perk_points is not None:
            new_perks_str = struct.pack('<I', perk_points)
            self.txt = self.replace_substring_inplace(self.txt, new_perks_str, perk_points_span)
            new_perk_points = struct.unpack("<I", self.txt[perk_points_span[0]:perk_points_span[1]])[0]
            print(f"{char_name}'s available perk points was updated from {current_perk_points} to {new_perk_points}.")
        else:
            print(f"{char_name} currently has {current_perk_points} available perk points.")
        if perk_checks is not None:
            perk_checks_str = struct.pack('<I', perk_checks)
            self.txt = self.replace_substring_inplace(self.txt, perk_checks_str, perk_checks_span)
            new_perk_checks = struct.unpack("<I", self.txt[perk_checks_span[0]:perk_checks_span[1]])[0]
            print(f"{char_name}'s available perk checks was updated from {current_perk_checks} to {new_perk_checks}.")
        else:
            print(f"{char_name} currently has {current_perk_checks} available perk checks.")

    def toggle_scenario_unlock(self, scenario=1, unlock=None):
        scenario_span = re.search(
            b"\x12Quest_Campaign_" + bytes(f"{scenario:03d}", "utf-8") + b"(.*?)\t", self.txt
        ).span(1)
        current_scenario_state = struct.unpack("<I", self.txt[scenario_span[1] - 4:scenario_span[1]])[0]
        if unlock is not None:
            if self.scenario_state_dict[current_scenario_state] in ("Locked", "Unlocked", "Blocked"):
                if unlock:
                    new_scenario_state_str = struct.pack('<I', 2)
                else:
                    new_scenario_state_str = struct.pack('<I', 1)
                scenario_state_span = (scenario_span[1] - 4, scenario_span[1])
                self.txt = self.replace_substring_inplace(self.txt, new_scenario_state_str, scenario_state_span)
                new_scenario_state = struct.unpack("<I", self.txt[scenario_span[1] - 4:scenario_span[1]])[0]
                cur_state = self.scenario_state_dict[current_scenario_state]
                new_state = self.scenario_state_dict[new_scenario_state]
                print(f"Scenario {scenario} was changed from {cur_state} to {new_state}.")
            else:
                print(f"Scenario {scenario} is currently {self.scenario_state_dict[current_scenario_state]}.")
                print("I can't change the state of such a scenario.")
        else:
            print(f"Scenario {scenario} is currently {self.scenario_state_dict[current_scenario_state]}.")

    def show_scenario_overview(self, verbose=False):
        scenarios = [m for m in re.finditer(b"\x12Quest_Campaign_([0-9]{3})([\s\S]*?\x00\x00\x00)\t", self.txt)]
        overview = {
            "Completed": [],
            "InProgress": [],
            "InProgressCasual": [],
            "Unlocked": [],
            "Locked": [],
            "Blocked": [],
            "None": [],
        }
        processed_scenarios = []
        for scenario in scenarios:
            scenario_nbr = int(scenario.group(1))
            scenario_state = struct.unpack("<I", scenario.group(2)[-4:])[0]
            if scenario_nbr in processed_scenarios:
                # this scenario was already processed
                pass
            else:
                overview[self.scenario_state_dict[scenario_state]].append(scenario_nbr)
                processed_scenarios.append(scenario_nbr)

        print("\nScenario Overview:")
        for k, v in overview.items():
            if (len(v) > 0 and k != "Locked") or verbose:
                print(f"    {k}: {' '.join([str(s) for s in v])}")

    def update_campaign_values(self, donated=None, prosperity=None, reputation=None):
        donated_span = re.search(b"GoldDonated", self.txt).span()
        donated_gold_span = (donated_span[1] + 6, donated_span[1] + 10)
        current_gold_donated = struct.unpack("<I", self.txt[donated_gold_span[0]:donated_gold_span[1]])[0]
        if donated is not None:
            new_gold_donated_str = struct.pack('<I', donated)
            self.txt = self.replace_substring_inplace(self.txt, new_gold_donated_str, donated_gold_span)
            print(
                f"The total gold donated to the tree was updated from {current_gold_donated:,}"
                f" gold to {donated} gold."
            )
        else:
            print(f"\nThere was {current_gold_donated:,} gold donated to the tree so far.")

        campaign_span = list(
            re.finditer(b"MapRuleLibrary\.Party\.CMapCharacter.*?\\t(.*?)\\t", self.txt)
        )[0].span(1)
        prosperity_span = (campaign_span[0] + 4, campaign_span[0] + 8)
        current_prosperity = struct.unpack("<I", self.txt[prosperity_span[0]:prosperity_span[1]])[0]
        if prosperity is not None:
            new_prosperity_str = struct.pack("<I", prosperity)
            self.txt = self.replace_substring_inplace(self.txt, new_prosperity_str, prosperity_span)
            print(f"Prosperity was updated from {current_prosperity} to {prosperity}.")
        else:
            print(f"Prosperity is currently at {current_prosperity}.")

        reputation_span = (campaign_span[0] + 8, campaign_span[1])
        current_reputation = struct.unpack("<I", self.txt[reputation_span[0]:reputation_span[1]])[0]
        if reputation is not None:
            new_reputation_str = struct.pack("<I", reputation)
            self.txt = self.replace_substring_inplace(self.txt, new_reputation_str, reputation_span)
            print(f"Reputation was updated from {current_reputation} to {reputation}.")
        else:
            print(f"Reputation is currently at {current_reputation}.")
