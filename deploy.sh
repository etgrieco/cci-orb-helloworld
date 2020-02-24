!#/bin/bash
circleci orb validate ./orb.yml
circleci orb publish ./orb.yml etgrieco/hello-world@dev:0.0.1
git add app.py
git add orb.yml
git commit -m "orb test"
git push
 
