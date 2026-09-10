import json
from pathlib import Path

path=Path('config.json')
config=json.loads(path.read_text())
config['default_category_target']=1
config['max_featured_per_team']=1
config['max_featured_per_source']=2
config.setdefault('category_targets',{}).update({
 'U.S. Politics':1,'U.S. News':1,'World News':2,'Conflicts & Security':1,
 'Middle East Affairs':1,'Health & Medicine':1,'AI & Technology':1,
 'Business & Economy':2,'Society & Culture':1,'Sports':2,'Good News':1
})
config.setdefault('category_limits',{}).update({
 'U.S. Politics':3,'U.S. News':3,'World News':4,'Conflicts & Security':3,
 'Middle East Affairs':3,'Health & Medicine':2,'AI & Technology':2,
 'Business & Economy':3,'Society & Culture':2,'Sports':2,'Good News':1
})
path.write_text(json.dumps(config,indent=2)+'\n')
print('Applied independent category targets and expansion limits.')
