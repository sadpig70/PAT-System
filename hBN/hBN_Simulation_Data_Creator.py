# pip install numpy pandas scipy
# python hbn_simulator.py hbn_large 5000

import sys
import numpy as np
import pandas as pd
from scipy.stats import norm

class HBNProcessSimulator:
    def __init__(self, seed=42, exp_data=None):
        """
        hBN 공정-구조-물성 시뮬레이션 데이터 생성기
        
        Parameters:
        seed (int): 랜덤 시드 (기본값 42)
        exp_data (DataFrame): 실험 데이터 (보정용, 기본값 None)
        """
        np.random.seed(seed)
        # 공정 변수 범위 (CVD 공정 기준)
        self.process_ranges = {
            'temperature': (1500, 1800),      # K
            'pressure': (1, 5),               # atm
            'growth_time': (30, 180),         # 분
            'boron_ratio': (0.05, 0.15)       # 몰비
        }
        # 실험 데이터 (보정용)
        self.exp_data = exp_data
        # 물성 범위 (실험값 기반, 분포 확장)
        self.property_ranges = {
            'crystallite_size': (400, 2200),      # nm
            'defect_density': (5e7, 2e10),        # cm⁻²
            'thermal_conductivity': (390, 460),   # W/m·K
            'bandgap': (5.85, 6.05)               # eV
        }

    def simulate(self, n_samples=1000):
        """
        hBN 시뮬레이션 데이터 생성
        
        Parameters:
        n_samples (int): 생성할 샘플 수 (기본값 1000)
        
        Returns:
        DataFrame: 공정 변수와 물성 데이터
        """
        # 1. 공정 변수 샘플링 (균일 분포)
        temp = np.random.uniform(*self.process_ranges['temperature'], n_samples)
        pressure = np.random.uniform(*self.process_ranges['pressure'], n_samples)
        time_ = np.random.uniform(*self.process_ranges['growth_time'], n_samples)
        boron = np.random.uniform(*self.process_ranges['boron_ratio'], n_samples)

        # 2. 결정립 크기: 온도, 시간, 압력, 비선형/임계현상 반영
        critical_temp = 1650  # 결정 성장 임계 온도 (K)
        grain_size = (
            0.7 * (temp - 1500) +
            1.2 * np.log1p(time_) -  # 시간 로그 스케일링
            60 * (pressure - 1) +
            300 * (temp > critical_temp) * np.exp((temp - critical_temp) / 80) +  # 임계 온도 이상 가속
            200 * np.sin(boron * np.pi * 4) +  # 주기적 변동
            np.random.normal(0, 120, n_samples)  # 실험 오차
        )
        grain_size = np.clip(grain_size, *self.property_ranges['crystallite_size'])

        # 3. 결함 밀도: 다변수 비선형 모델
        defect_density = (
            1.5e10 - 1.2e9 * np.tanh((temp - 1500) / 200) +  # 온도 비선형 효과
            - 4e9 * (boron - 0.05) / 0.1 +  # 보론비 선형 효과
            + 2.5e9 * np.sqrt(pressure) +  # 압력 제곱근 효과
            + 1e9 * (grain_size < 700) +  # 작은 결정립에서 결함 증가
            np.random.normal(0, 2e8, n_samples)  # 실험 오차
        )
        defect_density = np.clip(defect_density, *self.property_ranges['defect_density'])

        # 4. 열전도도: 결정립 크기, 결함 밀도 기반 비선형 모델
        thermal_cond = (
            412 + 
            0.024 * np.sqrt(grain_size - 400) +  # 결정립 크기 제곱근 효과
            - 1.2e-9 * (defect_density - 5e7) +  # 결함 밀도 선형 효과
            8 * np.tanh((grain_size - 1000) / 700) +  # 비선형 임계 효과
            np.random.normal(0, 2.5, n_samples)  # 실험 오차
        )
        thermal_cond = np.clip(thermal_cond, *self.property_ranges['thermal_conductivity'])

        # 5. 밴드갭: 결함, 온도, 압력 기반 모델
        bandgap = (
            5.97 - 
            1.5e-11 * (defect_density - 5e7) +  # 결함 밀도 효과
            0.01 * np.exp(-(temp - 1600) / 100) +  # 온도 지수 효과
            - 0.005 * (pressure - 1) +  # 압력 효과
            np.random.normal(0, 0.007, n_samples)  # 실험 오차
        )
        bandgap = np.clip(bandgap, *self.property_ranges['bandgap'])

        # 6. 실험 데이터 기반 보정 (있을 경우)
        if self.exp_data is not None:
            for col in ['crystallite_size', 'defect_density', 'thermal_conductivity', 'bandgap']:
                if col in self.exp_data.columns:
                    exp_mean = self.exp_data[col].mean()
                    sim_mean = np.mean(eval(col))
                    diff = exp_mean - sim_mean
                    # ±2% 이내로 평균값 보정
                    if abs(diff / exp_mean) > 0.02:
                        # 보정 적용
                        if col == 'crystallite_size':
                            grain_size += diff * 0.98
                        elif col == 'defect_density':
                            defect_density += diff * 0.98
                        elif col == 'thermal_conductivity':
                            thermal_cond += diff * 0.98
                        elif col == 'bandgap':
                            bandgap += diff * 0.98

        # 7. 데이터프레임 구성
        df = pd.DataFrame({
            'temperature': temp,
            'pressure': pressure,
            'growth_time': time_,
            'boron_ratio': boron,
            'crystallite_size': grain_size,
            'defect_density': defect_density,
            'thermal_conductivity': thermal_cond,
            'bandgap': bandgap
        })
        return df

    def check_experimental_agreement(self, df):
        """
        실험 데이터와의 일치도 검증
        
        Parameters:
        df (DataFrame): 시뮬레이션 데이터
        
        Returns:
        dict: 실험값과의 오차 리포트
        """
        if self.exp_data is None:
            return {"error": "실험 데이터가 없습니다."}
        
        report = {}
        for col in ['crystallite_size', 'defect_density', 'thermal_conductivity', 'bandgap']:
            if col in self.exp_data.columns:
                sim_mean = df[col].mean()
                exp_mean = self.exp_data[col].mean()
                error = abs(sim_mean - exp_mean) / exp_mean
                report[col] = {
                    'sim_mean': sim_mean,
                    'exp_mean': exp_mean,
                    'relative_error': error,
                    'within_2percent': error <= 0.02
                }
        return report

if __name__ == "__main__":
    # 명령행 인자 처리
    if len(sys.argv) < 2:
        print("사용법: python hbn_simulator.py [출력파일명] [샘플수]")
        print("예시: python hbn_simulator.py hbn_data 5000")
        sys.exit(1)
    
    # 파일명 추출
    output_filename = sys.argv[1]
    
    # 샘플 수 추출 (기본값 1000)
    n_samples = 1000
    if len(sys.argv) >= 3:
        try:
            n_samples = int(sys.argv[2])
        except ValueError:
            print("경고: 유효하지 않은 샘플 수. 기본값 1000 사용")
            n_samples = 1000

    # (선택) 실험 데이터 로드 - 실제 사용 시 주석 해제
    # exp_data = pd.read_csv('experimental_data.csv')
    exp_data = None  # 기본값

    # 시뮬레이터 초기화 및 데이터 생성
    simulator = HBNProcessSimulator(seed=42, exp_data=exp_data)
    df = simulator.simulate(n_samples)
    
    # CSV 파일 저장
    csv_filename = f"{output_filename}.csv"
    df.to_csv(csv_filename, index=False)
    print(f"[완료] {n_samples}개 샘플이 {csv_filename}에 저장되었습니다.")
    
    # 실험 데이터와 비교 (있을 경우)
    if exp_data is not None:
        agreement = simulator.check_experimental_agreement(df)
        print("\n[실험값 비교 리포트]")
        for prop, result in agreement.items():
            status = "통과" if result['within_2percent'] else "실패"
            print(f"{prop}: {status} (오차: {result['relative_error']*100:.2f}%)")

