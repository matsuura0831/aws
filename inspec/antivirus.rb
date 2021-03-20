control "Check antivirus software" do
  title "Check antivirus software is installed"

  if os.family == 'redhat'
    describe file('/opt/Symantec/symantec_antivirus/sav') do
      its('type') { should eq :file }
    end

    describe command('/opt/Symantec/symantec_antivirus/sav info -a') do
      its('stdout') { should eq "Enabled\n" }
      its('stderr') { should eq '' }
      its('exit_status') { should eq 0 }
    end
  end
end