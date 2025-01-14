"""Main module
# Resources
- Reference google sheets:
  https://docs.google.com/spreadsheets/d/17hHiqc6GKWv9trcW-lRnv-MhZL8Swrx2/edit#gid=1335629675
  https://docs.google.com/spreadsheets/d/1uroJbhMmOTJqRkTddlSNYleSKxw4i2216syGUSK7ZuU/edit?userstoinvite=joeflack4@gmail.com&actionButton=1#gid=435465078
"""
import json
import os
import pickle
from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Dict, List, OrderedDict

import pandas as pd

from value_set_vsac_to_json.config import CACHE_DIR, OUTPUT_DIR
from value_set_vsac_to_json.definitions.constants import FHIR_JSON_TEMPLATE, OMOP_JSON_TEMPLATE
from value_set_vsac_to_json.google_sheets import get_sheets_data
from value_set_vsac_to_json.vsac_api import get_ticket_granting_ticket, get_value_set, get_value_sets


# TODO: repurpose this to use VSAC format
def vsac_to_fhir(value_set: Dict) -> Dict:
    """Convert VSAC JSON dict to FHIR JSON dict"""
    d: Dict = copy(FHIR_JSON_TEMPLATE)
    d['id'] = int(value_set['valueSet.id'][0])
    d['text']['div'] = d['text']['div'].format(value_set['valueSet.description'][0])
    d['url'] = d['url'].format(str(value_set['valueSet.id'][0]))
    d['name'] = value_set['valueSet.name'][0]
    d['title'] = value_set['valueSet.name'][0]
    d['status'] = value_set['valueSet.status'][0]
    d['description'] = value_set['valueSet.description'][0]
    d['compose']['include'][0]['system'] = value_set['valueSet.codeSystem'][0]
    d['compose']['include'][0]['version'] = value_set['valueSet.codeSystemVersion'][0]
    concepts = []
    d['compose']['include'][0]['concept'] = concepts

    return d


# TODO: use depth to make this either nested JSON, or, if depth=1, concatenate
#  ... all intention sub-fields into a single string, etc.
# TODO:
def vsac_to_vsac(v: Dict, depth=2) -> Dict:     # this is the format @DaveraGabriel specified by looking at the vsac web interface
    """Convert VSAC JSON dict to OMOP JSON dict"""

    # Attempt at regexp
    # Clinical Focus: Asthma conditions which suggest applicability of NHLBI NAEPP EPR3 Guidelines for the Diagnosis and Management of Asthma (2007) and the 2020 Focused Updates to the Asthma Management Guidelines),(Data Element Scope: FHIR Condition.code),(Inclusion Criteria: SNOMEDCT concepts in "Asthma SCT" and ICD10CM concepts in "Asthma ICD10CM" valuesets.),(Exclusion Criteria: none)
    # import re
    # regexer = re.compile('\((.+): (.+)\)')  # fail
    # regexer = re.compile('\((.+): (.+)\)[,$]')
    # found = regexer.match(value_sets['ns0:Purpose'])
    # x1 = found.groups()[0]

    purposes = v['ns0:Purpose'].split('),')
    d = {
        "Concept Set Name": v['@displayName'],
        "Created At": 'vsacToOmopConversion:{}; vsacRevision:{}'.format(
            datetime.now().strftime('%Y/%m/%d'),
            v['ns0:RevisionDate']),
        "Created By": v['ns0:Source'],
        # "Created By": "https://github.com/HOT-Ecosystem/ValueSet-Converters",
        "Intention": {
            "Clinical Focus": purposes[0].split('(Clinical Focus: ')[1],
            "Inclusion Criteria": purposes[0].split('(Inclusion Criteria: ')[1],
            "Data Element Scope": purposes[0].split('(Data Element Scope: ')[1],
            "Exclusion Criteria": purposes[0].split('(Exclusion Criteria: ')[1],
        },
        "Limitations": {
            "Exclusion Criteria": "",
            "VSAC Note": None,  # VSAC Note: (exclude if null)
        },
        "Provenance": {
            "VSAC Steward": "",
            "OID": "",
            "Code System(s)": [],
            "Definition Type": "",
            "Definition Version": "",
        }
    }

    return d


def get_csv(value_sets: List[OrderedDict], field_delimiter=',', code_delimiter='|') -> pd.DataFrame:
    """get a list of codes"""
    rows = []
    for value_set in value_sets:
        name = value_set['@displayName']
        purposes = value_set['ns0:Purpose'].split('),')
        code_system_codes = {}
        for concept_dict in value_set['ns0:ConceptList']['ns0:Concept']:
            code = concept_dict['@code']
            code_system = concept_dict['@codeSystemName']
            if code_system not in code_system_codes:
                code_system_codes[code_system] = []
            code_system_codes[code_system].append(code)
        for code_system, codes in code_system_codes.items():
            row = {
                'name': name,
                'nameVSAC': '[VSAC] ' + name,
                'oid': value_set['@ID'],
                'codeSystem': code_system,
                'codes': code_delimiter.join(codes),
                'limitations': str(purposes[3]),
                'intention': str(purposes[0:2]),
                # 'intention': code_delimiter.join([x for x in intention_dict.values()]),
                # 'intention.json': intention_json_str,
                'provenance': {
                    'VSAC Steward': value_set['ns0:Source'],
                    'OID': value_set['@ID'],
                    'Code System(s)': ','.join(list(code_system_codes.keys())),
                    'Definition Type': value_set['ns0:Type'],
                    'Definition Version': value_set['@version'],
                    'Accessed': str(datetime.now())[0:-7]
                },
            }
            rows.append(row)

    # Create/Return DF & Save CSV
    df = pd.DataFrame(rows)
    outdir = os.path.join(OUTPUT_DIR, datetime.now().strftime('%Y.%m.%d'))
    if not os.path.exists(outdir):
        os.mkdir(outdir)
    outpath = os.path.join(outdir, 'list_of_codes.tsv')
    df.to_csv(outpath, sep=field_delimiter, index=False)

    return df


def run(
    artefact=['csv_fields', 'json', 'tsv_code'][2],
    format=['fhir', 'omop'][1],
    field_delimiter=[',', '\t'][0],  # TODO: add to cli
    code_delimiter=[',', ';', '|'][2],  # TODO: add to cli
    json_indent=4, use_cache=True):
    """Main function

    Args:
        file_path (str): Path to file
        json_indent (int): If 0, there will be no line breaks and no indents. Else,
        ...you get both.
    """
    value_sets = []
    pickle_file = Path(CACHE_DIR, 'value_sets.pickle')

    if use_cache:
        if pickle_file.is_file() and use_cache:
            value_sets = pickle.load(open(pickle_file, 'rb'))
        else:
            use_cache = False
    if not use_cache:
        # 1. Get OIDs to query
        # TODO: Get a different API_Key for this than my 'ohbehave' project
        df: pd.DataFrame = get_sheets_data()
        object_ids: List[str] = [x for x in list(df['OID']) if x != '']

        # 2. Get VSAC auth ticket
        tgt: str = get_ticket_granting_ticket()
        # service_ticket = get_service_ticket(tgt)

        value_sets_dict: OrderedDict = get_value_sets(object_ids, tgt)
        value_sets: List[OrderedDict] = value_sets_dict['ns0:RetrieveMultipleValueSetsResponse'][
            'ns0:DescribedValueSet']

        with open(pickle_file, 'wb') as handle:
            pickle.dump(value_sets, handle, protocol=pickle.HIGHEST_PROTOCOL)

    if artefact == 'tsv_code':
        get_csv(value_sets, field_delimiter, code_delimiter)
    elif artefact == 'json':
        # Populate JSON objs
        d_list: List[Dict] = []
        for value_set in value_sets:
            value_set2 = {}
            if format == 'fhir':
                value_set2 = vsac_to_fhir(value_set)
            elif format == 'omop':
                value_set2 = vsac_to_vsac(value_set)
            d_list.append(value_set2)

        # Save file
        for d in d_list:
            valueset_name = d['name']
            with open(valueset_name + '.json', 'w') as fp:
                if json_indent:
                    json.dump(d, fp, indent=json_indent)
                else:
                    json.dump(d, fp)
    elif artefact == 'csv_fields':
        pass

if __name__ == '__main__':
    run()