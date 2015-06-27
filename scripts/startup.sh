# create repository
#    git init
#    touch .gitignore
#    git add .gitignore
#    git commit -m "Initial commit"

repos="\
git://github.com/devcurmudgeon/ybd.git \
git://git.baserock.org/baserock/baserock/definitions.git \
git://git.baserock.org/baserock/baserock/infrastructure.git \
git://git.baserock.org/baserock/baserock/morphs.git"

for repo in $repos; do
    basename=${repo##*/}; name=${basename%.git}
    git remote add -f $name $repo
    git merge -s ours --no-commit $name/master
    git read-tree --prefix=$name/ -u $name/master
    git commit -m "Subtree merged in $name"
    # git pull -s subtree $name [branchname]
done
