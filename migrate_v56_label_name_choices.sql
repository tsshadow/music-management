-- migrate_v56_label_name_choices.sql
--
-- Release info enrichment, the owner's decision on #164 (docs/designs/release-info-enrichment/).
-- The importer places a release no catalogue rule routes under the existing label folder its .nfo
-- names. Where the owner's own filing disagrees -- releases whose .nfo says `Cloud 9 Music` sit in
-- `Cloud 9 Dance` -- it must not move: it records a proposal carrying both folders, and the choice,
-- made once per label, places every later release with that .nfo label.
--
--   rules_label_name_choices -- per .nfo label (folded, services/importer/label_match.fold):
--       name_folder     the folder the name maps to,
--       history_folder  the folder the owner filed such releases in most often,
--       history_count / name_count  how many label-tree releases sit in each,
--       chosen_folder   the owner's choice (NULL until made); never touched by a re-learn.
--   rules_label_proposals.alternative_label / label_choice_key -- the second option a proposal
--       offers, and the choice row its confirmation answers.
--
-- Seeded with the 104 pairs measured on production on 2026-10-02 over the 42.196 .nfo files of the
-- label tree; `python -m services.importer.label_history --apply` re-learns them from the library.
-- Re-runnable and expand-only: CREATE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, INSERT IGNORE.

CREATE TABLE IF NOT EXISTS rules_label_name_choices (
    nfo_label_key VARCHAR(191) NOT NULL PRIMARY KEY,
    nfo_label VARCHAR(255) NOT NULL,
    name_folder VARCHAR(255) NOT NULL,
    history_folder VARCHAR(255) NOT NULL,
    history_count INT NOT NULL DEFAULT 0,
    name_count INT NOT NULL DEFAULT 0,
    examples TEXT NULL,
    chosen_folder VARCHAR(255) NULL,
    decided_at TIMESTAMP NULL,
    learned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE rules_label_proposals
    ADD COLUMN IF NOT EXISTS alternative_label VARCHAR(255) NULL;

ALTER TABLE rules_label_proposals
    ADD COLUMN IF NOT EXISTS label_choice_key VARCHAR(191) NULL;

INSERT IGNORE INTO rules_label_name_choices
    (nfo_label_key, nfo_label, name_folder, history_folder, history_count, name_count, examples)
VALUES
    ('acidreign', 'Acid Reign', 'Acid Reign', 'Aggressive Records', 1, 207, 'AR000 - Boray_-_Get_Loose_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('activa', 'Activa', 'Activa', 'Activa Shine', 9, 104, 'ACTSH032 - Activator-Veteran_Of_Style_Volume_4-(ACTSH032)-WEB-2015-UKHx | ACTSH034 - Activator-Veteran_Of_Style_Vol_4__Sampler_2-(ACTSH034)-WEB-2015-UKHx'),
    ('actuation', 'Actuation', 'Actuation', 'This Is Hardstyle', 1, 4, 'TIH000 - Frontliner_And_LePrince_-_Mad_Sound_Killer_(Extended_Mix)-SINGLE-WEB-2023-FMC'),
    ('annihilation', 'Annihilation Records', 'Annihilation', 'Annihaltion Records', 12, 23, 'ARSR012 - Akimbo_-_Back_To_The_Oldschool_(Original_Mix)-(ARSR12)-24BIT-WEB-FLAC-2024 | ARSR012 - Akimbo_-_Back_To_The_Oldschool-(ARSR12)-WEB-2024'),
    ('babyboom', 'Babyboom Records', 'Babyboom Records', 'Babys Back', 1, 13, 'BABY026 - Black_Knight-Back_To_Tha_O_School-(BABY026)-16BIT-WEB-FLAC-2008-AOVF_Classics'),
    ('barbaric', 'Barbaric Records', 'Barbaric Records', 'Bounce Back Records', 48, 337, 'BBR165 - Eraized_-_Control_The_Night_(Extended_Mix)-(BBR165)-WEB-2025 | BBR163 - Akimbo_-_Down_On_The_Floor_(Extended_Mix)-(BBR163)-WEB-FLAC-2025'),
    ('beatdealer', 'Beat Dealer Records', 'Beat Dealer Records', 'One Seventy', 1, 8, 'ONESEVENTY178 - Mike_Reverie_and_Ben_Journiee_-_Without_You_(Edit)-(ONESEVENTY178)-WEB-2023'),
    ('blackbox', 'Blackbox Digital', 'Blackbox Digital', 'Industrial Strength', 3, 166, 'ISR045 - Third_Orbit_-_Underground_Love_(Edits)-(ISR045)-WEB-2024 | ISR046 - Third_Orbit_and_Adventum_-_Nevermind_(The_Unknown_Remix)-(ISR046)-WEB-2024'),
    ('bounceback', 'Bounce Back records', 'Bounce Back Records', 'Barbaric Records', 55, 75, 'BBR089 - Sonic_Rampage_-_House_Of_Rampage_Anthem_(Edit)-(BBR089)-WEB-2025 | BBR098 - Violent_Suspect_and_Fraternity_-_Demon_(Edit)-(BBR098)-WEB-FLAC-2026'),
    ('brandstichters', 'Brandstichters', 'Brandstichters', 'B2S', 1, 4, 'BS220035 - Ransom_and_Buren_van_De_Brandweer_-_Foempen_(Incl._Extended_Mix)-()-WEB-NL-2023-JUSTiFY_iNT'),
    ('breaktherules', 'Break The Rules Records', 'Break The Rules', 'Bring the riot', 159, 35, 'BTR126 - Vainez_-_Straight_Through_My_Vainez-(BTR126)-SINGLE-WEB-2025-SRG | BTR140 - Sabotage_-_Louder_(Edit)-(BTR140)-WEB-FLAC-2026'),
    ('brutalforce', 'Brutal Force', 'Brutal Force Records', 'Barong Family', 71, 89, 'BF-192 - Dj_Salvo_-_Ecstacy_Of_Hardcore-(BF-192)-WEB-2025 | BF000 - Razorback_-_All_Day_Every_Day-WEB-2023'),
    ('bzrk', 'BZRK Records', 'BZRK', 'Pengo Records', 1, 38, 'PENGO012 3-Steps_Ahead_-_Drop_it_(incl_Bass_D_and_King_Matthew)-CDS-1999-Pro'),
    ('caputmundi', 'caput mundi', 'Caput Mundi Records', 'Crypton Music', 1, 0, 'CM003 - Zatox_-_Burnin_Up_(Original_Mix)-(CM003)-WEB-2024'),
    ('cloud9', 'Cloud 9 Recordings', 'Cloud 9 Music', 'Cloud 9 Dance', 24, 1, 'CLDM2025001 - VA-Masters_Of_Hardcore_Chapter_XLVII_Temple_Of_Resonance-(CLDM2025001)-2CD-FLAC-2025-OTT | CLDM2025001 - VA-Masters_Of_Hardcore_Chapter_XLVII_Temple_Of_Resonance-(CLDM2025001)-2CD-2025-OTTS'),
    ('colors', 'Colors Music', 'Colors Music', 'Respect Hardstyle', 4, 17, 'RESPECTHARDSTYLE001DJ - System_Of_Zolden_-_Majestic_(Extended_Mix)-(RESPECTHARDSTYLE001DJ)-WEB-2025 | RESPECTHARDSTYLE002DJ - Sedutchion_and_Stereocode_-_Spectrum_(Extended_Mix)-(RESPECTHARDSTYLE002DJ)-WEB-2025'),
    ('dancetunes', 'Dance Tunes Digital', 'Dance Tunes BV', 'QDance', 1, 2, 'VA-Qlimax_2007_The_Compilation-WEB-Readnfo-2007-Homely'),
    ('darkdescent', 'Dark. Descent', 'Dark Descent', 'Dark. Decent.', 7, 5, 'DD00135 - VA_-_Into_The_Dark_Lands-(DD00135)-WEB-FLAC-2024 | DD13138 - Mental_Fear_Productions_-_Falling-(DD13138)-WEB-2024'),
    ('defqon1', 'Defqon.1 Records', 'Defqon.1 Records', 'Power Hour Records', 1, 120, 'PH016 - Gezellige_Uptempo-Vogeltjesdans-(PH016)-NL-16BIT-WEB-FLAC-2024-AOVF'),
    ('delict', 'Delict Records', 'Delict Records', 'Masters Of Hardcore', 1, 2, 'MOHDIGI000 - D-Fence_-_Brainshock-WEB-2021'),
    ('delirium', 'Delirium Music', 'Delirium Music', 'Deathmatch Music', 2, 5, 'DM001 - Clockartz_-_Not_The_One-(DM001)-WEB-2024-SRG | DLM015DJ - Clockartz_-_The_Phantom_Of_The_Opera--SINGLE-WEB-2020-SRG'),
    ('dequinox', 'Dequinox', 'Dequinox Music', 'Dirty Workz', 1, 187, 'DWX000 - Retribute_-_Rolling_To_The_Rhythm-WEB-2024'),
    ('derailedtraxx', 'Derailed Traxx', 'Derailed Traxx', 'Dance Tunes BV', 46, 174, 'DT177DR1 - Ephoric_-_Enlightenment_(Volture_Remix)-(DT177DR1)-WEB-2023-SRG | DT283D - VENNIC_-_The_Fire_In_My_Heart-(DT283D)-WEB-2025-FMC'),
    ('dfence', 'D-Fence', 'D-Fence Records', 'Masters Of Hardcore', 1, 0, 'MOHDIGI000 - D-Fence_-_In_The_Place-WEB-FLAC-2021'),
    ('dimitrik', 'Dimitri K Records', 'Dimitri K Records', 'Drillkore Records', 1, 1, 'DKR001 - Dimitri_K_-_To_The_Death_(Mix_Version)-(DKR001)-24BIT-WEB-FLAC-2023'),
    ('dirtyworkz', 'Dirty Workz', 'Dirty Workz', 'label', 2, 2010, '- Digital_Mindz_And_Nightcraft_-_Origins_Of_Chaos_(Genesis_2024_Anthem)_(Edit)-SINGLE-WEB-2024-UTNG | - Sub_Zero_Project_-_Maze_Of_Memories_(Reverze_Anthem_2024)_(Edit)-SINGLE-WEB-2024-UTNG'),
    ('distrokid', 'DistroKid', 'DistroKid', 'Maxtreme', 2, 2, 'MXTRM033 - Maxtreme_-_Kicking_You_Out_(Original_Mix)-(MXTRM033)-WEB-2025 | MXTRM033 - Maxtreme_-_Kicking_You_Out_(Original_Mix)-(MXTRM033)-WEB-FLAC-2025'),
    ('drokz', 'Drokz Digital', 'Drokz', 'Terrorheads', 1, 22, 'TERRORHEADS_004 - Drokz_-_Beast_Of_The_Beast-(TERRORHEADS_004)-WEB-2023'),
    ('dutchmasterworks', 'Dutch Master Works', 'Dutch Master Works', 'Dutch Master Works Hybrid', 11, 449, 'DMWH024 - Lowriders_-_Dont_Get_Back_(Fahjah_And_NAHSYK_Rework)-(DMWH024)-SINGLE-WEB-2025-SRG | DMWH013 - Swbk_-_Never_Give_Up_(Edit)-()-WEB-2023'),
    ('dwarf', 'Dwarf', 'Dwarf Records', 'Barong Family', 1, 73, 'BF000 - Jony_K_-_Higher-WEB-2024'),
    ('endofline', 'End Of Line Recordings', 'End of line', 'Minus Is More', 1, 362, 'MINUS222 - RVAGE_-_Turn_Up_The_Bass_(Extended_Mix)-(MINUS222)-WEB-2024'),
    ('enzyme', 'Enzyme Records', 'Enzyme Records', 'Enzyme X', 7, 35, 'ENZYMEX_18 Enzyme_X_-_Prankster_and_Problem_Child-(ENZYME_X_18)-Vinyl-2004-SQ | ENZYMEX_19 Enzyme_X_-_Dissimulation_and_Fytoftora-(ENZYME_X_19)-PROPER-Vinyl-2005-SQ'),
    ('enzymex', 'Enzyme X', 'Enzyme X', 'Enzyme Records', 2, 10, 'CDE2010 Enzyme_X_-_Component_2-2CD-2010-SQ | CDE2009 VA_-_Enzyme_X_-_Component_1-2CD-2009-SQ'),
    ('exitushardcore', 'Exitus hardcore', 'Exitus Hardcore', 'Exit Records', 12, 2, 'EXT44 - Dj_Syndrome_-_The_Soap-(EXT44)-WEB-2024 | EXT49 - Dj_Syndrome_-_The_Devil_In_The_Mirror-(EXT49)-WEB-FLAC-2025'),
    ('fearless', 'Fearless Records', 'Fear Less Music', 'Freestyle', 6, 9, 'FR025 - Asow_and_Milski_-_Kickdealer-(FR025)-WEB-2025 | FR035B - Asow_and_Nutkix_-_Nothing_To_Lose_(Extended_Mix)-(FR035B)-WEB-FLAC-2025'),
    ('gabberhead', 'Gabberhead', 'Gabberhead Records', 'Cyndium Records', 1, 35, 'CR058 - Biodome_and_Gabberhead_-_Show_Me_What_You_Got-WEB-2024'),
    ('gearbox', 'Gearbox', 'Gearbox Digital', 'Gearbox Overdrive', 3, 602, 'GBO184 - Udow_And_MT_-_Back_In_The_Day-(GBO184)-WEB-FLAC-2026 | GBO182 - Tharoza_-_Addicted_To_The_Bass-(GBO182)-WEB-FLAC-2026'),
    ('gearboxeuphoria', 'Gearbox Euphoria', 'Gearbox Euphoria', 'Gearbox Digital', 2, 173, 'GBE154 - Re-Pulze_-_Out_In_The_Rain_(Edit)-()-WEB-2022 | GBE146 - MELOX_-_Focus_Your_Spirit_(Extended_Mix)-()-WEB-2022'),
    ('gearboxrevolutions', 'Gearbox Revolutions', 'Gearbox Revolutions', 'Gearbox Euphoria', 1, 302, 'GBE000 - Heavy_Resistance_-_Dont_Mind_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('ggm', 'GGM Digital', 'GGM Digital', 'GGM RAW Records', 4, 64, 'GGMRAW004 VA_-_GGMRAW_004-(GGMRAW004)-WEB-2011-VELOCiTY | GGMRAW005 VA_-_GGM_RAW_005-(GGMRAW005)-WEB-2012-VELOCiTY'),
    ('ggmraw', 'GGM Raw Records', 'GGM RAW Records', 'GGM Digital', 6, 5, 'GGMRAW003 VA_-_GGM_Raw_Records_003-(GGM_RAW_003)-Vinyl-2008-SQ | DJ_Smurf-Exposure_King_(The_Trumpet_Song)-WEB-2009-1KING'),
    ('guillotine', 'Guillotine Recordings', 'Guillotine Recordings', 'H2oh Recordings', 1, 6, 'H2O36 - Predator_-_Out_Of_Control-()-WEB-2023'),
    ('handkcuf', 'Handkcuf Records', 'Handkcuf Records', 'Derailed Traxx', 1, 23, 'HAKCDG004 - DJ_LX_-_The_Unbeaten_Path-(HAKCDG004)-WEB-2020-SRG'),
    ('hard', 'Hard Music Records', 'HARD Music', 'Hard Music Records Raw', 9, 2, 'HMR110 - High_Level_Ft_Mark_and_Alex_-_Wellerman_(Original_Mix)-()-WEB-2022 | HMR111 - High_Level_-_Family_2022_(Extended_Mix)-()-WEB-2022'),
    ('hardcoreblasters', 'Hardcore Blasters', 'Hardcore Blasters', 'Hardcore Blasters Jump', 6, 40, 'JUMP02CD VA-Jump_2_-_The_Second_Hardcore_Attack-CD-2000-Homely | JUMP01CD VA-Jump_-_The_Hardcore_Attack-CD-2000-Homely'),
    ('hardcorefrance', 'Hardcore France', 'Hardcore France', 'Hardstyle France', 3, 213, 'HF000 - Maissouille_-_Hoist_Your_Colors_(Extented_Mix)-WEB-2021 | HSF186DJ - Neko_-_Aftermath_(Anthem_Eskape_2025)_(Extended_Mix)-(HSF186DJ)-WEB-2025'),
    ('hardstylefrance', 'Hardstyle France Records', 'Hardstyle France', 'Head Fuck Records', 4, 218, 'HDF159DJ - Overage_-_Lionheart_(Edit)-(HDF159DJ)-WEB-FLAC-2026 | HDF159DJ - Overage_-_Lionheart_(Extended_Mix)-(HDF159DJ)-WEB-2026'),
    ('iamfrenchcore', 'I Am Frenchcore', 'I Am Frenchcore', 'Infected Records', 8, 10, 'IFR14 - Radium_and_The_Sequel_and_Sprinky_-_I_Am_Frenchcore_14-(IFR14)-WEB-2023 | IFR18 - Radium_and_Goetia_-_I_Am_Frenchcore_18-(IFR18)-WEB-2025'),
    ('iamhardstyle', 'I Am Hardstyle', 'I AM HARDSTYLE', 'I AM HARDSTYLE - Amplify', 4, 326, 'IAHA031D - Mark_Eva_ft._Aelinn-ReMarkEvable-(IAHA031D)-16BIT-WEB-FLAC-2023-AOVF | IAHA039D - Shinzo-Best_You_Had-(IAHA039D)-16BIT-WEB-FLAC-2024-AOVF'),
    ('ignition', 'Ignition Digital', 'Ignition Digital', 'Gearbox Overdrive', 1, 138, 'GBO000 - Triple_X_-_This_Is_X_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('industrialstrength', 'Industrial Strength Records', 'Industrial Strength', 'Indus3 Records', 1, 120, 'ISRD_191 - CodeRed_-_Tornado_Strike-()-WEB-2022'),
    ('intents', 'Intents Records', 'Intents Records', 'TOFF Music', 2, 58, 'TOFF073 - VA_-_Intents_Festival_2023-Kingdom_Of_Unity-(TOFF073)-WEB-2023-SRG | TOFF089D - VA_-_Intents_Festival_Rise_Of_Titans-(TOFF089D)-WEB-2026-FMC'),
    ('italianhardstyle', 'Italian Hardstyle', 'Italian Hardstyle', 'Scantraxx', 1, 54, 'SCCD024 - Zatox_-_Unstoppable-(SCCD024)-WEB-2023-SRG'),
    ('keepitup', 'Keep It Up Music', 'Keep it up', 'Revealed Recordings', 1, 44, 'REVR916B - AndyG-Wake_Up_(Extended_Mix)-(REVR916B)-SINGLE-WEB-2023-AOV'),
    ('kontor', 'Kontor', 'Kontor Records', 'Neox Music Records', 2, 4, 'NMR001 - NeoX_feat_Killer_MC_-_Surviving_the_Slums-SINGLE-WEB-2019-FMC | NMR002 - NeoX_-_Collabs_(Part_1)-WEB-2019-FMC'),
    ('mastersofhardcore', 'Masters of Hardcore', 'Masters Of Hardcore', 'Snakepit Music', 1, 557, 'SPM000 - Irradiate_-_HIT_IT_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('monolyth', 'Monolyth', 'Monolyth', 'Monolith', 12, 6, 'MYST_-_Way_Of_The_Warrior_(Edit)-SINGLE-WEB-2023-UTNG | Monolyth  - MYST_-_Palace_In_The_Clouds_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('monstersofcore', 'Monsters Of Core Records', 'Monsters Of Core', 'Monsters Of Terrorcore Records', 26, 20, 'MONSTER070 - Revolxist_-_Street_Beat_EP-()-WEB-2022 | MONSTER077 - RU1_-_My_Instinct-()-WEB-2022'),
    ('neox', 'NeoX Music Records', 'Neox Music Records', 'Neophyte Records', 1, 132, 'NMR029 - Noize_Frequencies_-_VIRUS-()-SINGLE-WEB-2021-SRG_iNT'),
    ('nexxus', 'NeXxus', 'Nexxus', 'Scantraxx', 1, 70, 'SCAN000 - Bright_Visions_-_I_GOT_THIS_(Edit)-SINGLE-WEB-2024-UTNG'),
    ('nightbreed', 'Nightbreed', 'Nightbreed Records', 'Nightbreed Nocturnal', 9, 90, 'NBQ117 - Myst-Trinity-()-WEB-2021-AOV | NBN040 - Degos_and_Re-Done_-_Diving_(Hardstyle_Remix)-SINGLE-WEB-2019-FMC'),
    ('nrg', 'NRG Records', 'NRG Records', 'Dirty Workz', 2, 50, 'DWX1499 - Araysen_-_Hopes_(Incl_Extended_Mix)-(DWX1499)-WEB-2024-SPiDeR | DWX1499 - Araysen_-_Hopes_(Edit)-SINGLE-WEB-2024-UTNG'),
    ('peacock', 'Peacock Records', 'Peacock Records', 'Project Chaos Records', 8, 137, 'PCR097 - Deathroar_-_Neon_Soul_EP-(PCR097)-WEB-FLAC-2023 | PCR095 - Deathroar_-_Sing_Me_To_Sleep_EP_(Edits)-(PCR095)-WEB-2023'),
    ('peacocksexclusives', 'Peacock''s Exclusives', 'Peacocks Exclusives', 'Peacock Records', 3, 2, 'PCR000 - Dr_Peacock_and_DJ_Panda_-_Its_a_Dream_2k19-SINGLE-WEB-2019-FMC | Dr._Peacock_and_D-Frek_-_Drink-WEB-2022'),
    ('powerhour', 'Power Hour Records', 'Power Hour Records', 'Black Mirror Society', 1, 26, 'BMS000 - Phuture_Noize_-_Statues-WEB-2022-SRG'),
    ('projectchaos', 'Project Chaos Records', 'Project Chaos Records', 'Peacock Records', 39, 3, 'PCR013DJ - The_Executer_-_The_World_Play_Dumb_(Extended_Mix)-(PCR013DJ)-WEB-FLAC-2025 | PCR022DJ - The_Executer_-_Rhythm_Of_The_Universe_(Edit)-(PCR022DJ)-WEB-FLAC-2026'),
    ('prototypes', 'Prototypes Records', 'Prototypes Records', 'Partyraiser Records', 44, 2, 'PR150 - 161_-_Smile_For_The_Camera-(PR150)-WEB-FLAC-2026 | PR145 - Vein_-_Tears-(PR145)-WEB-2026-SRG'),
    ('puremassive', 'Pure-Massive-Records', 'Pure Massive Records', 'Pussy Lounge Music', 1, 50, 'PM045 - Dj_Maniac_-_Dreams-()-WEB-2022'),
    ('qdance', 'Q-Dance', 'QDance', 'Defqon.1 Records', 2, 323, 'DQ088 - VA-Defqon.1_Power_Of_The_Tribe_(Album_Mix)-(DQ088)-CD-2024-OTTS | DQ008 - VA-Defqon.1_Power_Of_The_Tribe_Album_Mix-(DQ008)-CD-FLAC-2024-OTT'),
    ('ravenrg', 'RAVE NRG', 'Rave NRG', 'RAVEN', 1, 2, 'RVN001 - Advanced_Dealer_and_Rave_NRG_-_Trancecore_4.0_(Edit)-(RVN001)-WEB-2024'),
    ('rebirthevents', 'REBiRTH Events Records', 'REBiRTH Events Records', 'TOFF Music', 2, 61, 'TOFF083 - VA_-_Rebirth_Festival_2025-(TOFF083)-WEB-2025-SRG | TOFF076 - VA_-_Rebellion_2023-The_Eclipse-(TOFF076)-WEB-2023-SRG'),
    ('rebl', 'Rebl Records', 'Rebl Records', 'Cloud 9 Dance', 1, 61, 'CLDG2024001 - Outsiders_and_Restrained_and_Maintain_-_Warhorn_(E2_We_Rise_Or_Fall)-(CLDG2024001)-WEB-2024'),
    ('revealed', 'Revealed', 'Revealed Recordings', 'ROQ n Rolla', 1, 68, 'Dr_Phunk_-_Fool_Us_All-WEB-2020-QMI'),
    ('rotterdam', 'Rotterdam Records', 'Rotterdam Records', 'Traxtorm', 1, 110, 'TRAXCD06 The_Stunned_Guys_-_SHE-Stunning_Hardcore_Elements-1998-UPE'),
    ('roughrecruits', 'Rough Recruits', 'Rough Recruits', 'Roughstate', 1, 156, 'ROUGHR082 - Voidax_and_Dawnfire_-_Madness-(ROUGHR082)-WEB-2020'),
    ('roughstate', 'Roughstate', 'Roughstate', 'Rough Recruits', 2, 297, 'ROUGH000 - Adaro_And_Level_One_Ft._Nino_Lucarelli_-_One_And_The_Same-WEB-2023-SRG | ROUGHR000 - Frequencerz_-_Ascend-WEB-2022-SRG'),
    ('savagesquad', 'Savage Squad Recordings', 'Savage Squad Recordings', 'Savage Squad Recordings OZ', 3, 232, 'SSROZ006D - Adverze_-_Lock_and_Load_(Edit)-()-WEB-2022 | SSROZ007D - Deviouz_-_Rage_EP_(Edits)-()-WEB-2022'),
    ('scantraxx', 'Scantraxx Records', 'Scantraxx', 'Cloud 9 Dance', 1, 592, 'CLDM2008076  VA-Scantraxx Unreleased Volume 1-WEB-2008-Homely'),
    ('scantraxxblack', 'Scantraxx Black', 'Scantraxx Black', 'Scantraxx', 2, 188, 'SCAN000 - Imperatorz_-_Energy_(Edit)-SINGLE-WEB-2023-UTNG | SCAN464D - A-RIZE-Voices_(Original_Mix)-(SCAN464D)-SINGLE-WEB-2023-AOV'),
    ('scantraxxcovers', 'Scantraxx Covers', 'Scantraxx Covers', 'Scantraxx', 1, 2, 'SCAN000 - Demi_Kanon_-_Castle_In_The_Sky-WEB-2023'),
    ('scantraxxprospexx', 'Scantraxx Prospexx', 'Scantraxx Prospexx', 'Scantraxx', 4, 386, 'PRSPX000 -  - Lalou_-_Into_The_Night_(Edit)-SINGLE-WEB-2023-UTNG | SCANTRAXX000 - Keku_And_VLTGE-We_Are_Not_Alone-SINGLE-WEB-2022-AOV'),
    ('scantraxxsilver', 'Scantraxx Silver', 'Scantraxx Silver', 'label', 1, 227, '- Bright_Visions_-_Fire_From_Within_(2023_Edit)_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('sefa', 'Sefa Music', 'Sefa Music', 'Spline Music', 11, 7, 'SM012D - Sefa_And_Devin_Wild_-_Into_Space-(SM012D)-SINGLE-WEB-2024-FMC | SM007D - Sefa_and_Vertile_-_Battlefield_(Extended_Mix)-(SM007D)-WEB-2024'),
    ('seismic', 'Seismic', 'Seismic Records', 'Seismic Special', 1, 2, 'SMCSP001 The_Beholder_and_Balistic-The_Decibel_Anthem-Vinyl-2002-UTE'),
    ('sinphony', 'SINPHONY', 'Sinphony', 'Supreme Intelligence', 11, 7, 'SIN079 - Tony_Junior_and_Unresolved_-_Together_As_One_(Extended_Mix)-(SIN079)-WEB-FLAC-2024 | SIN084 - Timmy_Trumpet_and_GPF_and_Dikke_Baap_-_Techno_Pieps_(Extended_Mix)-(SIN084)-WEB-2025'),
    ('smashedsociety', 'Smashed Society', 'Smashed Society', 'Smash Records', 1, 77, 'SMASH000 - Ruff_Limits_And_Nick_Novity_-_Breaking_Away_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('smashthehouse', 'Smash The House', 'Smash The House', 'Smash Records', 2, 8, 'STH223RMXBP - VA-She_Knows_(3_Are_Legend_x_Mandy_Extended_Remix)-(STH223RMXBP) | STH262BP - Dimitri_Vegas_And_Like_Mike_X_Bassjackers-Happy_Together_(Toneshifterz_Extended_Remix)-()-SINGLE-WEB-2023-AOV'),
    ('snakepit', 'Snakepit Music', 'Snakepit Music', 'Masters Of Hardcore', 1, 251, 'MOHDIGI448 - Dither_And_Major_Conspiracy_And_MC_Livid_-_Party_Life_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('tc', 'TC Records', 'TC Records', 'TC Labs', 3, 205, 'TCLABS000 - Criminal_Mayhem_-_Drowning-WEB-2021 | TCLABS000 - Criminal_Mayhem_-_Lobotomy-WEB-2021'),
    ('tclabs', 'TC Labs', 'TC Labs', 'TC Records', 1, 293, 'TCREC010 - Aversion_-_Global_Revolution-SINGLE-WEB-2020-FMC'),
    ('terrormachine', 'Terror Machine', 'Terror Machine Records', 'Upcoming Records', 1, 39, 'Viciouz_-_Ghetto_King-WEB-2022'),
    ('theracords', 'Theracords', 'Theracords', 'TC Records', 1, 109, 'TCREC000 - VA_-_Theracords_6_(2013_2014)-WEB-2021-JUSTiFY_iNT'),
    ('thirdmovement', 'The Third Movement', 'The Third Movement', 'Promo Test', 3, 285, 'PROTEST000 - Promo_-_Dancefloor_Hardcore_(Hysta_Remix)-WEB-2023 | PROTEST000 - Promo_-_What_The_Fuck_(D-passion_Remix)-WEB-2023'),
    ('traxtorm', 'Traxtorm', 'Traxtorm', 'Traxtorm Records Sinful Edition', 1, 147, 'TRSE015 Meccano_Twins-The_Last_Release-(TRSE15)-Vinyl-2004-DOC'),
    ('triplesix', 'Triple Six Records', 'Triple Six Records', 'Partyraiser Records', 2, 223, 'PR205 - DRS_and_Sakyra_-_Brutality_(Extended_Mix)-(PR205)-WEB-FLAC-2026 | PR205 - DRS_and_Sakyra_-_Brutality_(Extended_Mix)-(PR205)-WEB-2026'),
    ('twofingershigh', 'Two Fingers High Records', 'Two Fingers High', 'Maxtreme', 3, 2, 'MXTRM033 - Maxtreme_-_Kicking_You_Out_(Edit)-(MXTRM033)-WEB-2025 | MXTRM032 - Maxtreme_-_Dont_Stop_the_Party_(Edits)-(MXTRM032)-WEB-2025'),
    ('unfold', 'Unfold Records', 'Unfold Music', 'Undefined Music', 1, 301, 'UM020 - Oxya_-_Embrace_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('unlocked', 'Unlocked Records', 'Unlocked Records', 'Unleashed Records', 1, 14, 'UNLR005 - Oxya_-_Fire-()-SINGLE-WEB-2021-SRG'),
    ('upcoming', 'Upcoming Records', 'Upcoming Records', 'Underground Industry Records', 1, 440, 'UIPR000 - BASSFREQ_-_Ballin_(Edit)-SINGLE-WEB-2023-UTNG'),
    ('vip', 'Vip Records', 'Vip Records', 'VIP Classics', 12, 12, 'VIPCL1029 VA_-_Vip_Classics_29-(VIPCL1029)-Vinyl-2005-SQ | VIPCL1022 VA_-_Vip_Classics_22-(VIPCL1022)-Vinyl-2005-SQ'),
    ('wardog', 'Wardog', 'Wardog Records', 'label', 1, 29, '- RVRS_-_Poison_(2024_Hardstyle_Remix)_(Edit)-SINGLE-WEB-2024-UTNG'),
    ('wer', 'We R', 'WE R', 'I AM HARDSTYLE', 2, 62, 'IAHCD001Brennan_Heart-Show_Your_True_Colors-PROPER-2CD-2019-D2H | IAH001 - Brennan_Heart_-_Show_Your_True_Colors_(I_AM_HARDSTYLE_2019_Anthem)-(IAH001D)-WEB-2019-FMC'),
    ('xsv', 'XSV Music', 'XSV Music', 'K.N.O.R. Records', 1, 2, 'KN043-2 VA-The_KNOR_Collection_Volume_6-1996-dcg'),
    ('zeroday', 'Zero Day Records', 'Zero Day Records', 'Zoo Digital', 1, 2, 'ZD000 - D-Stort_-_That_Place-WEB-2023');
