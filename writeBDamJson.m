function writeBDamJson(path,value)
fid = fopen(path,"w"); assert(fid >= 0,"Cannot write %s",path);
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,"%s\n",jsonencode(value,PrettyPrint=true));
end
