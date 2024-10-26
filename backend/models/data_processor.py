import numpy as np
import pandas as pd
import random
import yaml


class DataProcessorV0:
    """
    Базовая заглушка
    """
    def process(self, transactions: pd.DataFrame, clients: pd.DataFrame):
        clients['gndr'] = clients['gndr'].replace({'ж': 0, 'м': 1})
        self.processed_data = clients[['accnt_id', 'brth_yr', 'prsnt_age', 'gndr', 'erly_pnsn_flg']].astype(
            {
                'brth_yr': 'int64',
                'prsnt_age': 'int64',
                'gndr': 'int64',
                'erly_pnsn_flg': 'int64',
            }
        )
        return self.processed_data


class DataProcessorV1:
    """
    Исходный датасет, только клиенты
    """
    def __init__(self):
        with open('./backend/models/configs/processor_v1.yaml', 'r') as file:
            self.config = yaml.safe_load(file)

    def process(self, transactions: pd.DataFrame, clients: pd.DataFrame):
        clients_columns_typing = self.config['data']['columns']['clients']
        clients_columns = list(self.config['data']['columns']['clients'].keys())

        clients = clients[clients_columns]

        clients['gndr'] = clients['gndr'].map({'ж': 0, 'м': 1})
        clients['accnt_bgn_date'] = clients['accnt_bgn_date'].astype(np.int64) // 1e9
        clients['accnt_status'] = clients['accnt_status'].map({'Накопительный период': 0, 'Выплатной период': 1})
        # le = LabelEncoder()
        # clients['prvs_npf'] = le.fit_transform(clients['prvs_npf'])
        # le = LabelEncoder()
        # clients['brth_plc'] = le.fit_transform(clients['brth_plc'])
        # clients['addrss_type'] = clients['addrss_type'].map({'Адрес места жительства': 0, 'Адрес по прописке': 1, 'Адрес для информирования': 2, 'Адрес за пределами РФ': 3})
        clients['okato'] = clients['okato'].fillna('0').apply(lambda x: str(x)[:2])
        clients['phn'] = clients['phn'].map({'нет': 0, 'да': 1})
        clients['email'] = clients['email'].map({'нет': 0, 'да': 1})
        clients['lk'] = clients['lk'].map({'нет': 0, 'да': 1})
        clients['assgn_npo'] = clients['assgn_npo'].map({'нет': 0, 'да': 1})
        clients['assgn_ops'] = clients['assgn_ops'].map({'нет': 0, 'да': 1})

        self.processed_data = clients.astype(
            clients_columns_typing
        )

        return self.processed_data

class DataProcessorV2:
    def process(self, transactions: pd.DataFrame, clients: pd.DataFrame, mode: str = 'inference'):
        clients['gndr'] = clients['gndr'].map({'ж': 0, 'м': 1})
        clients['phn'] = clients['phn'].map({'нет': 0, 'да': 1})
        clients['email'] = clients['email'].map({'нет': 0, 'да': 1})
        clients['lk'] = clients['lk'].map({'нет': 0, 'да': 1})
        clients['assgn_npo'] = clients['assgn_npo'].map({'нет': 0, 'да': 1})
        clients['assgn_ops'] = clients['assgn_ops'].map({'нет': 0, 'да': 1})

        clients['accnt_bgn_date'] = pd.to_datetime(clients['accnt_bgn_date'])
        # Возраст на момент подписания договора
        clients['age_agreement_start'] = clients['accnt_bgn_date'].dt.year - clients['brth_yr']

        # Флаг наличия пред организации
        clients['prvs_npf_flg'] = clients['prvs_npf'].case_when(([(~clients['prvs_npf'].isnull(), 1),
                                                        (clients['prvs_npf'].isnull(), 0),
                                    ]))

        # Исключаем клиентов, которые подписали договор после законного возраста выхода на пенсию
        #!!!!
        if mode == 'train':
            clients.drop(index = clients[clients['age_agreement_start'] > clients['pnsn_age']].index, inplace=True)

        # Дата начала выплат
        clients_on_pension = clients[clients['accnt_status'] == 'Выплатной период'].copy()
        clients_on_pension['accnt_end_date'] = clients_on_pension['accnt_bgn_date'] + clients_on_pension['cprtn_prd_d'].apply(lambda x: pd.to_timedelta(x, unit = 'days'))

        clients_not_on_pension = clients[clients['accnt_status'] == 'Накопительный период'].copy()
        clients_not_on_pension['accnt_end_date'] = pd.to_datetime('2030-01-01')
        clients = clients.merge(pd.concat([clients_on_pension, clients_not_on_pension]).loc[:, ['clnt_id', 'accnt_end_date']], on='clnt_id', how='inner')

        # Флаг нахождения на пенсии
        clients['on_pension_flg'] = clients['erly_pnsn_flg'].case_when([(clients['erly_pnsn_flg'] == 1, 1),
                                    ((clients['erly_pnsn_flg'] == 0) & (clients['accnt_status'] =='Накопительный период'), 0),
                                    ((clients['erly_pnsn_flg'] == 0) & (clients['accnt_status'] =='Выплатной период'), 1)
                                    ])


        # Добавляем дату выхода на пенсию по закону
        clients['accnt_expected_end_date'] = clients['accnt_bgn_date'] + (clients['pnsn_age'] - clients['age_agreement_start']).apply(lambda x: pd.to_timedelta(int(x)*365, unit = 'days'))

        # Добавляем дату отсчета (клиент в прошлом)
        clients['accnt_past_date'] = clients['erly_pnsn_flg'].case_when(([
            (clients['erly_pnsn_flg'] == 0,  #when
                clients['accnt_bgn_date'] + ((clients['accnt_expected_end_date'] - clients['accnt_bgn_date']).dt.days)\
                                        .apply(lambda x: pd.to_timedelta(int(x * random.uniform(0.2, 0.7)), unit='days'))   #then
            ),
            (clients['erly_pnsn_flg'] == 1,  #when
                clients['accnt_bgn_date'] + ((clients['accnt_end_date'] - clients['accnt_bgn_date']).dt.days)\
                                        .apply(lambda x: pd.to_timedelta(int(x * random.uniform(0.2, 0.7)), unit='days'))   #then
            )
        ]))
        clients['accnt_past_date'] = pd.to_datetime(clients['accnt_past_date'])
        clients['accnt_past_age'] = clients['accnt_past_date'] - clients['accnt_bgn_date']
        
        clients['accnt_past_date'] = clients['accnt_past_date'].astype(np.int64) // 1e9
        clients['accnt_bgn_date'] = clients['accnt_bgn_date'].astype(np.int64) // 1e9

        clients_columns = [
            'accnt_id',
            'gndr',
            'prsnt_age',
            'accnt_bgn_date',
            'pnsn_age',
            #'prvs_npf',
            'prvs_npf_flg',
            'okato',
            'phn',
            'email',
            'lk',
            'assgn_npo',
            'assgn_ops',

            'accnt_past_date',
            'accnt_past_age',
            'age_agreement_start',
            'accnt_expected_end_date',

            'erly_pnsn_flg'
        ]
        preprocessed_data = clients[clients_columns]
        self.processed_data = preprocessed_data.astype(
            {
                'accnt_id': 'str',
                'gndr': np.int64,
                'prsnt_age': np.int64,
                'accnt_bgn_date': np.int64,
                'pnsn_age': np.int64,
                #'prvs_npf',
                'prvs_npf_flg': np.int64,
                'okato': np.int64,
                'phn': np.int64,
                'email': np.int64,
                'lk': np.int64,
                'assgn_npo': np.int64,
                'assgn_ops': np.int64,

                'accnt_past_date': np.int64,
                'accnt_past_age': np.int64,
                'age_agreement_start': np.int64,
                'accnt_expected_end_date': np.int64,

                'erly_pnsn_flg': np.int64
            }
        )

        return self.processed_data

df = pd.read_csv('sample_cntrbtrs_clnts_ops_trn-3.csv', sep = ';', encoding = 'cp1251')

preprocessed = DataProcessorV2().process(clients = df, transactions=None)
print(preprocessed)
