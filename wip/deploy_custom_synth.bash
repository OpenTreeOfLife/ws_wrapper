#!/bin/bash
set -x
home="/home/deploy"
custom_to_serve_par="${home}/ws_dir/data/custom"
if ! test -d "${custom_to_serve_par}" ; then
	mkdir -p "${custom_to_serve_par}" || exit
fi
launch_par="${home}/ws_dir/cpp_apps/local/bin"
if ! test -d "${launch_par}" ; then
	mkdir -p "${launch_par}" || exit
fi

tag="${1}"
url="${2}"
if ! test -d "${custom_to_serve_par}/${tag}/${tag}" ; then
 	mkdir -p "${custom_to_serve_par}/${tag}/" || exit
 	if ! test -d scratch ; then
 		mkdir scratch || exit
 	fi
 	cd scratch || exit
 	curl "${url}" --output "${tag}.tar.gz" || exit
 	tar xfvz "${tag}.tar.gz" -C "${custom_to_serve_par}/${tag}" || exit
 	cd ..
fi
launch_script="${launch_par}/launch_otc_ws_${tag}.sh"
if ! test -f "${launch_script}" ; then
cat << EOF >>"${launch_script}"
#!/bin/bash
if pgrep otc-tol-ws >/dev/null ; then
    if test -f "/home/deploy/ws_dir/data/wspidfile.txt" ; then
        pkill -F "/home/deploy/ws_dir/data/wspidfile.txt" --signal=9 otc-tol-ws || exit
    else
        pgrep otc-tol-ws > "/home/deploy/ws_dir/data/wspidfile.txt"
        pkill -F "/home/deploy/ws_dir/data/wspidfile.txt" --signal=9 otc-tol-ws || exit
    fi
fi
if test -f "/home/deploy/ws_dir/data/wspidfile.txt" ; then
    rm "/home/deploy/ws_dir/data/wspidfile.txt" || exit
fi

echo -n "Starting otcetera web services (otc-tol-ws)... "
export LD_LIBRARY_PATH="/home/deploy/ws_dir/local/library:\${LD_LIBRARY_PATH}"
export PATH="/usr/sbin:\${PATH}"

daemonize \\
    -c "/home/deploy/ws_dir/data" \\
    "/home/deploy/ws_dir/local/bin/otc-tol-ws" \\
    "/home/deploy/ws_dir/data/custom/${tag}/${tag}/subott_dir" \\
    "-D/home/deploy/ws_dir/data/custom/${tag}" \\
    "-p/home/deploy/ws_dir/data/wspidfile.txt" \\
    -P1984 \\
    --num-threads=4 || exit


nt=0
while true ; do
    sleep 1
    if test -f "/home/deploy/ws_dir/data/wspidfile.txt" ; then
        echo "otc-tol-ws launched as daemon with pid" \$(cat "/home/deploy/ws_dir/data/wspidfile.txt")
        exit 0
    fi
    if ! pgrep otc-tol-ws >/dev/null ; then
        echo "otc-tol-ws could not be launched"
    fi
    if test \$nt -gt 400 ; then
        echo "otc-tol-ws not launched after 400 seconds, aborting..."
        exit 2
    fi
    nt=\$(expr \$nt + 1)
done

EOF
fi
bash "${launch_script}" || exit
