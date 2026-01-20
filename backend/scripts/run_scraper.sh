source ../.venv/bin/activate
#nohup python full_scoring_flow_db.py --output-dir out --only-null-trustscore --cert-start A --cert-end E > out/output1.log 2>&1 
#nohup python full_scoring_flow_db.py --output-dir out --only-null-trustscore --cert-start F --cert-end J > out/output2.log 2>&1 
#nohup python full_scoring_flow_db.py --output-dir out --only-null-trustscore --cert-start K --cert-end O > out/output3.log 2>&1 
nohup python full_scoring_flow_db.py --output-dir out --only-null-trustscore --cert-start P --cert-end T > out/output4.log 2>&1
nohup python full_scoring_flow_db.py --output-dir out --only-null-trustscore --cert-start U --cert-end Z > out/output5.log 2>&1

